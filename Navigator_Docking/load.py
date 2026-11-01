# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Docking Navigator: independent pad guidance and docking explanations for EDMC.

GPL-3.0-or-later. See NOTICE.txt for upstream pad-layout acknowledgements.
"""
from __future__ import annotations

import logging
import json
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
import myNotebook as nb
from config import appname, config
from .core import DockingState, event_age, starport_position, valid_pad
from .render import exterior, interior, interior_flat, carrier, render_scene

TITLE = "(N) Docking"
HEADER_TITLE = "Docking"
VERSION = "0.4.9"
PREFIX = "DockingNavigator_"
logger = logging.getLogger(f"{appname}.Navigator_Docking")
_model = DockingState()
_view = None
_hidden_panel_widgets = []
_root = None
_pending = None
_expiry = None
_bindings = []
_prefs = {}
_stopped = True

# Station mode: shown only around stations, other panels collapsed meanwhile.
COLLAPSE_GLYPHS = ("🔼", "🔽")      # standard EDMC plugin collapse/expand button text
NFZ_ENTERED = "$STATION_NoFireZone_entered"
NFZ_EXITED = "$STATION_NoFireZone_exited"
END_EVENTS = {"Docked", "SupercruiseEntry", "StartJump", "FSDJump", "CarrierJump",
              "Died", "Shutdown", "LoadGame", "Location"}
_active = False
_collapsed_by_us: list = []
# Warning-only mode: a denial far from the station (e.g. Reason "Distance", which the game
# logs without any DockingRequested) shows the hidden panel briefly without station mode.
_alert = False
BOOL_PREFS = ("auto_show", "denial_alert", "collapse_others", "diagram", "hints", "reverse", "three_d", "auto_pad")


def _settings():
    return {
        "diagram": config.get_bool(PREFIX + "Diagram", default=True),
        "hints": config.get_bool(PREFIX + "Hints", default=True),
        "reverse": config.get_bool(PREFIX + "Reverse", default=False),
        "three_d": config.get_bool(PREFIX + "ThreeD", default=True),
        "auto_pad": config.get_bool(PREFIX + "AutoPad", default=False),
        "size": max(180, min(480, config.get_int(PREFIX + "Size", default=320) or 320)),
        "seconds": max(5, min(60, config.get_int(PREFIX + "Seconds", default=15) or 15)),
        "auto_show": config.get_bool(PREFIX + "AutoShow", default=True),
        "denial_alert": config.get_bool(PREFIX + "DenialAlert", default=True),
        # Preserve the old combined choice until this independent setting is saved.
        "collapse_others": config.get_bool(PREFIX + "CollapseOthers", default=config.get_bool(PREFIX + "AutoShow", default=True)),
    }


def _text_colours(widget, dark):
    if dark:
        return (config.get_str("dark_text", default="#ff8000"),
                config.get_str("dark_highlight", default="white"))
    # Default theme uses EDMC's system palette, rather than its dark settings.
    try:
        from theme import theme
        current = theme.current or {}
    except (ImportError, AttributeError):
        current = {}
    return (current.get("foreground") or ttk.Style(widget).lookup("TLabel", "foreground") or "SystemWindowText",
            current.get("highlight") or "blue")


class DockingView(tk.Frame):
    """A stable-height diagram; repainting never asks EDMC to resize itself."""
    def __init__(self, parent):
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.titlebar = tk.Frame(self)
        self.title_label = tk.Label(self.titlebar, text=HEADER_TITLE, anchor="w", justify="left")
        self.title_label.pack(side="left", expand=True, fill="x")
        self.modebar = tk.Frame(self.titlebar)
        self.modebar.pack(side="right")
        self.header = tk.Label(self, text=HEADER_TITLE, anchor="center", justify="center")
        self.pad_font = tkfont.Font(self, font="TkDefaultFont")
        self.selected_font = tkfont.Font(self, font="TkDefaultFont", underline=True)   # selected mode/stage
        self.station = tk.Label(self, anchor="center", justify="center")
        self.message = tk.Label(self, anchor="center", justify="center")
        self.hint = tk.Label(self, anchor="center", justify="center")
        self.canvas = tk.Canvas(self, width=240, height=240, highlightthickness=0, borderwidth=0)
        self.caption = tk.Label(self, anchor="center", justify="center")
        self.toolbar = tk.Frame(self)
        self.buttons = {}
        for name, command in (("2D", lambda: self._mode(False)), ("3D", lambda: self._mode(True)),
                              ("Entrance", lambda: self._stage('entrance')), ("Pad", lambda: self._stage('pad')),
                              ("Reset view", self._reset_camera)):
            label = tk.Label(self.modebar if name in {'2D', '3D'} else self.toolbar, text=name, cursor="hand2", padx=6, takefocus=True)
            label.pack(side="left")
            for sequence in ('<Button-1>', '<Return>', '<space>'):
                label.bind(sequence, lambda event, callback=command: self._activate(callback))
            self.buttons[name] = label
        for row, widget in enumerate((self.titlebar, self.header, self.station, self.message, self.hint, self.toolbar, self.canvas, self.caption)):
            widget.grid(row=row, column=0, sticky="ew", pady=(0, 2))
        self.signature = None
        self.model = DockingState()
        self.options = _settings()
        self.stage = 'entrance'
        self.camera = (28, -18)
        self.zoom = 1
        self.session_key = None
        self.render_key = None
        self.photo = None
        self.preview = False
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._save_camera)
        self.canvas.bind("<MouseWheel>", self._zoom)
        self.canvas.bind("<Configure>", lambda event: self._draw())

    @staticmethod
    def _activate(callback):
        callback()
        return 'break'

    def _mode(self, three_d):
        if not self.preview:
            config.set(PREFIX + "ThreeD", bool(three_d))
            if "three_d" in _prefs:
                try:
                    _prefs["three_d"].set(bool(three_d))
                except tk.TclError:
                    pass
        self.options = {**self.options, "three_d": bool(three_d)}
        self.signature = None
        self.render(self.model, self.options)

    def _stage(self, stage):
        if stage == 'pad' and (self.model.phase != 'granted' or valid_pad(self.model.pad, self.model.layout) is None):
            return
        self.stage = stage
        self.signature = None
        self.render(self.model, self.options)

    def _save_camera(self, event=None):
        if not self.preview:
            try:
                cameras = json.loads(config.get_str(PREFIX+"Cameras",default="{}"))
            except (ValueError,TypeError):
                cameras = {}
            cameras[self.model.layout or "unknown"] = [*self.camera,self.zoom]
            config.set(PREFIX+"Cameras",json.dumps(cameras))
        return 'break'

    def _load_camera(self):
        self._reset_camera(save=False)
        try:
            saved=json.loads(config.get_str(PREFIX+"Cameras",default="{}")).get(self.model.layout or "unknown")
            if saved and len(saved)==3:
                yaw,pitch,zoom=map(float,saved)
                self.camera=(yaw%360,max(-75,min(75,pitch)))
                self.zoom=max(.65,min(1.5,zoom))
                self.render_key=None
        except (ValueError,TypeError,AttributeError):
            pass

    def _reset_camera(self, save=True):
        self.camera = (28, 52 if self.model.layout in {'carrier', 'squadron', 'colony'} else -18)
        self.zoom = 1
        self.render_key = None
        self._draw()
        if save: self._save_camera()

    def _drag_start(self, event):
        self.drag_origin = (event.x, event.y, *self.camera)
        return 'break'

    def _drag(self, event):
        if self.options['three_d'] and hasattr(self, 'drag_origin'):
            x, y, yaw, pitch = self.drag_origin
            self.camera = ((yaw+(event.x-x)*.65) % 360, max(-75, min(75, pitch+(event.y-y)*.5)))
            self._draw()
        return 'break'

    def _zoom(self, event):
        self.zoom = max(.65, min(1.5, self.zoom + (.08 if event.delta > 0 else -.08)))
        self._draw()
        self._save_camera()
        return 'break'

    def render(self, model, options):
        self.model, self.options = model, options
        try:
            key = self.winfo_toplevel().attributes("-transparentcolor")
        except tk.TclError:
            key = ""
        background = str(key or self.cget("background"))
        dark = bool(key) or config.get_int("theme", default=0) != 0
        normal_text, highlighted_text = _text_colours(self, dark)
        colour = {"denied": "#e45c52", "timeout": "#e45c52", "granted": "#24b56b", "docked": "#24b56b"}.get(model.phase, "#ff8c00" if dark else "#925000")
        session_key = (model.phase, model.station, model.market_id, model.pad)
        if session_key != self.session_key:
            self.session_key = session_key
            self.stage = 'pad' if model.phase == 'granted' and options['auto_pad'] else 'entrance'
            self._load_camera()
        # Suite menu rule: every control is clickable (Highlighted); the selected mode/stage is underlined.
        selected = {name for name in self.buttons
                    if name == ('3D' if options['three_d'] else '2D') or name.casefold() == self.stage}
        button_font = self.title_label.cget("font")
        wanted = dict(tkfont.Font(self, font=button_font).actual(), underline=True)
        if self.selected_font.actual() != wanted:
            self.selected_font.configure(**wanted)
        button_fonts = {name: str(self.selected_font) if name in selected else str(button_font)
                        for name in self.buttons}
        signature = (tuple(model.__dict__.items()), tuple(options.items()), background, dark, self.stage,
                     normal_text, highlighted_text, str(button_font))
        if (signature == self.signature and str(self.header.cget("foreground")) == colour
                and str(self.title_label.cget("foreground")) == normal_text
                and all(str(label.cget("foreground")) == highlighted_text
                        and str(label.cget("font")) == button_fonts[name] for name, label in self.buttons.items())
                and str(self.message.cget("foreground")) == colour
                and str(self.header.cget("font")) == str(self.pad_font)
                and str(self.canvas.cget("background")) == background):
            return
        self.signature = signature
        self.dark = dark
        size = options["size"]
        normal = tkfont.nametofont("TkDefaultFont", root=self).actual()
        self.pad_font.configure(family="Euro Caps" if dark else normal["family"],
                                size=13 if dark else (normal["size"] + 3 if normal["size"] > 0 else normal["size"] - 3),
                                weight="bold")
        self.configure(background=background)
        for widget in (self.title_label, self.header, self.station, self.message, self.hint, self.caption):
            widget.configure(wraplength=max(240, size), background=background)
        self.header.configure(foreground=colour, font=self.pad_font)
        self.title_label.configure(foreground=normal_text)
        self.toolbar.configure(background=background)
        self.titlebar.configure(background=background)
        self.modebar.configure(background=background)
        for name, label in self.buttons.items():
            label.configure(background=background, foreground=highlighted_text,
                            font=self.selected_font if name in selected else button_font)
        self.message.configure(foreground=colour)
        self.station.configure(foreground=normal_text, font=self.pad_font)
        self.hint.configure(foreground=normal_text)
        self.caption.configure(foreground=normal_text)
        self.canvas.configure(background=background, width=size, height=size)
        headings = {"idle": "Ready", "pending": "Docking Requested", "denied": "Docking Denied",
                    "timeout": "Docking Timed Out", "cancelled": "Docking Cancelled", "docked": "Docked"}
        heading = f"PAD {model.pad:02d} · Docking Granted" if model.phase == "granted" and model.pad else headings.get(model.phase, "Docking Granted")
        self.header.configure(text=heading)
        self.station.configure(text=model.display_station or model.station)
        self.message.configure(text=model.message)
        self.hint.configure(text=model.hint)
        active = model.phase != "idle"
        for widget, show in ((self.header, active), (self.station, active and bool(model.station)),
                             (self.message, active and bool(model.message)),
                             (self.hint, active and options["hints"] and bool(model.hint))):
            widget.grid() if show else widget.grid_remove()
        diagram = (options["diagram"] and model.phase in {"pending", "granted"} and bool(model.layout)
                   and (self.stage == 'entrance' or (model.pad is not None and valid_pad(model.pad, model.layout) is not None)))
        for widget in (self.toolbar, self.canvas, self.caption):
            widget.grid() if diagram else widget.grid_remove()
        if diagram:
            if model.layout == "starport" and self.stage == 'pad':
                _, _, sector, ring = starport_position(model.pad, options["reverse"])
                clock = ((sector + 6) % 12) or 12
                self.caption.configure(text=f"PAD {model.pad:02d} · schematic bay highlight\n"
                                            f"{clock} o'clock sector · {('outer', 'middle', 'inner')[ring]} reference ring\n"
                                            "Reference view · no live ship/station pose")
            elif model.layout == 'starport':
                caption = "MAILSLOT · orange entrance marker" if model.station_type.casefold() in {'coriolis', 'orbis', 'ocellus', 'bernal'} else "Generic station schematic · entrance marker"
                self.caption.configure(text=caption+"\n"
                                            "Reference view · drag to orbit; not a live bearing\n"
                                            "Select Pad when you are ready for the interior.")
            else:
                name = {"carrier": "Fleet carrier", "squadron": "Squadron carrier", "colony": "Colonisation ship"}[model.layout]
                self.caption.configure(text=f"{name} · deck reference (no mailslot)\n"
                                            "Reference view · no live ship/station pose")
            self._draw()
        else:
            self.canvas.delete("all")

    def _draw(self):
        model, options = self.model, self.options
        if (not options["diagram"] or model.phase not in {"pending", "granted"}
                or not model.layout or (self.stage == 'pad' and valid_pad(model.pad, model.layout) is None)):
            self.canvas.delete("all")
            self.photo = None
            self.render_key = None
            return
        width = max(1, min(self.canvas.winfo_width(), options['size']+80))
        height = max(1, self.canvas.winfo_height())
        is_carrier = model.layout in {'carrier', 'squadron', 'colony'}
        yaw, pitch = self.camera if options['three_d'] else ((0, 90) if is_carrier else (0, 0))
        key = (width, height, self.stage, model.layout, model.station_type, model.pad,
               options['reverse'], options['three_d'], yaw, pitch, self.zoom, getattr(self, 'dark', False))
        if key == self.render_key:
            return
        self.render_key = key
        if is_carrier:
            scene = carrier(model.layout, model.pad if self.stage == 'pad' else None, options['reverse'])
        elif self.stage == 'pad':
            scene = interior(model.pad, options['reverse']) if options['three_d'] else interior_flat(model.pad, options['reverse'])
        else:
            scene = exterior(model.station_type, options['reverse'])
        raster = render_scene(scene, width, height, yaw, pitch, options['three_d'], self.zoom, getattr(self, 'dark', False))
        self.photo = tk.PhotoImage(master=self, data=raster.png(), format='png')
        self.canvas.delete("all")
        tags = ('wireframe', 'assigned_pad') if scene.has_pad else ('wireframe', 'mailslot' if scene.has_slot else 'deck')
        self.canvas.create_image(self.canvas.winfo_width()/2, self.canvas.winfo_height()/2, image=self.photo, tags=tags)


def _render():
    global _pending
    _pending = None
    if not _stopped and _view is not None and _view.winfo_exists():
        _view.render(_model, _settings())


def _schedule(event=None):
    global _pending
    if _stopped or _root is None or config.shutting_down:
        return
    if event is not None:
        try:
            if event.widget.winfo_toplevel() is not _root:
                return
        except tk.TclError:
            return
    if _pending is None:
        _pending = _root.after_idle(_render)


def _cancel_expiry():
    global _expiry
    if _expiry is not None and _root is not None:
        try:
            _root.after_cancel(_expiry)
        except tk.TclError:
            pass
    _expiry = None


def _expire():
    global _expiry
    _expiry = None
    _model.reset()
    _end_alert()
    _schedule()


def _arm_expiry():
    global _expiry
    _cancel_expiry()
    if _root is not None and _model.phase in {"denied", "timeout", "cancelled", "docked", "pending"}:
        seconds = 60 if _model.phase == "pending" else (5 if _model.phase in {"docked", "cancelled"} else _settings()["seconds"])
        _expiry = _root.after(seconds * 1000, _expire)


def _inside(widget, container) -> bool:
    while widget is not None:
        if widget is container:
            return True
        widget = getattr(widget, "master", None)
    return False


def _other_collapse_buttons() -> list:
    """Standard 🔼/🔽 collapse buttons of the other plugins in EDMC's main window."""
    found, pending = [], list(_root.winfo_children()) if _root is not None else []
    while pending:
        widget = pending.pop()
        try:
            kind = widget.winfo_class()
            if kind == "Toplevel" or (_view is not None and _inside(widget, _view)):
                continue
            if kind == "Button" and str(widget.cget("text")).strip() in COLLAPSE_GLYPHS:
                found.append(widget)
            pending.extend(widget.winfo_children())
        except tk.TclError:
            continue
    return found


def _set_panel_visible(show: bool) -> None:
    if _view is None:
        return
    try:
        if show:
            for widget in _hidden_panel_widgets:
                if widget.winfo_exists(): widget.grid()
            _hidden_panel_widgets.clear()
            if _view.winfo_manager() != "pack": _view.grid()
            return
        _view.grid_remove()
        wrapper = _view.master
        # Only EDMC's named plugin wrapper and its separator belong to us.
        if wrapper.winfo_name().startswith("plugin_") and wrapper.winfo_manager()=="grid":
            suffix=wrapper.winfo_name()[7:]
            siblings=wrapper.master.children
            preceding=int(wrapper.grid_info()["row"])-1
            separator=next((item for item in siblings.values()
                            if item.winfo_name().startswith("plugin_hr")
                            and item.winfo_manager()=="grid"
                            and int(item.grid_info()["row"])==preceding),None)
            if separator is None:
                separator=siblings.get("plugin_hr_"+suffix) or siblings.get("plugin_hr"+suffix)
            for widget in (wrapper,separator):
                if widget is not None and widget.winfo_manager()=="grid":
                    widget.grid_remove()
                    if widget not in _hidden_panel_widgets: _hidden_panel_widgets.append(widget)
    except tk.TclError:
        pass


def _show_alert() -> None:
    """Show only the denial (no station mode, other panels untouched) while hidden."""
    global _alert
    if _active or _stopped or not _settings()["auto_show"] or not _settings()["denial_alert"]:
        return
    _alert = True
    _set_panel_visible(True)
    logger.info("Docking denial shown outside station mode")


def _end_alert() -> None:
    """Hide again after a warning-only display, unless station mode has taken over."""
    global _alert
    if not _alert:
        return
    _alert = False
    if not _active and _settings()["auto_show"]:
        _set_panel_visible(False)


def _activate(reason: str) -> None:
    """Entering a station: show this panel and collapse the other expanded panels,
    remembering exactly which ones we collapsed."""
    global _active, _alert
    if _active or _stopped:
        return
    _active = True
    _alert = False   # station mode now owns the panel
    if _settings()["collapse_others"]:
        _collapse_other_panels()
    _set_panel_visible(True)
    logger.info("Station mode on (%s): collapsed %d panel(s)", reason, len(_collapsed_by_us))


def _collapse_other_panels():
    for button in _other_collapse_buttons():
        try:
            if str(button.cget("text")).strip() == "🔼":      # expanded -> press to collapse
                button.invoke()
                if button not in _collapsed_by_us:
                    _collapsed_by_us.append(button)
        except tk.TclError:
            pass


def _restore_other_panels():
    restored = 0
    for button in _collapsed_by_us:
        try:
            if button.winfo_exists() and str(button.cget("text")).strip() == "🔽":
                button.invoke()
                restored += 1
        except tk.TclError:
            pass
    _collapsed_by_us.clear()
    return restored


def _deactivate(reason: str) -> None:
    """Docked / left / jumped away: re-open only the panels we collapsed (and only if they
    are still collapsed - anything you changed yourself is left alone), then hide again."""
    global _active
    if not _active:
        return
    _active = False
    restored = _restore_other_panels()
    if _settings()["auto_show"]:
        _set_panel_visible(False)
    logger.info("Station mode off (%s): restored %d panel(s)", reason, restored)


def _station_mode(entry: dict) -> None:
    event = entry.get("event")
    message = str(entry.get("Message") or "")
    fresh = event_age(entry) <= 120          # ignore old events while EDMC catches up
    if event == "ReceiveText" and message.startswith(NFZ_ENTERED) and fresh:
        _activate("no-fire zone entered")
    elif event == "ReceiveText" and message.startswith(NFZ_EXITED):
        _deactivate("no-fire zone left")
    elif event in ("DockingRequested", "DockingGranted") and fresh:
        _activate(event)                     # backup: EDMC started inside the zone
    elif event == "DockingDenied" and fresh:
        _show_alert()                        # e.g. too far away: no request was logged
    elif event in END_EVENTS or (event == "Music" and entry.get("MusicTrack") == "MainMenu"):
        _deactivate(event)
        _end_alert()


def plugin_start3(plugin_dir):
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def plugin_app(parent):
    global _view, _root, _stopped
    if _view is not None:
        return _view
    _root = parent.winfo_toplevel()
    _stopped = False
    _view = DockingView(parent)
    for sequence in ("<Configure>", "<Map>", "<<ThemeChanged>>"):
        _bindings.append((sequence, _root.bind(sequence, _schedule, add="+")))
    _schedule()
    _arm_expiry()
    # Hidden until you reach a station (EDMC places the panel first, then we hide it).
    _root.after_idle(lambda: _set_panel_visible(_active or not _settings()["auto_show"]))
    return _view


def journal_entry(cmdr, is_beta, system, station, entry, state):
    _station_mode(entry)
    if _model.handle(entry):
        _arm_expiry()
        _schedule()


def plugin_stop():
    global _root, _view, _pending, _stopped, _alert
    _deactivate("EDMC closing")              # never leave other panels collapsed
    _alert = False
    _stopped = True
    _cancel_expiry()
    if _root is not None:
        if _pending is not None:
            try:
                _root.after_cancel(_pending)
            except tk.TclError:
                pass
        for sequence, binding in _bindings:
            try:
                _root.unbind(sequence, binding)
            except tk.TclError:
                pass
    _bindings.clear()
    _pending = _root = _view = None
    _model.reset()


def _preview(parent):
    popup = tk.Toplevel(parent)
    popup.title(f"{TITLE} Preview")
    choices = ttk.Frame(popup); choices.pack(fill="x", padx=8, pady=8)
    kind = tk.StringVar(popup, value="Starport")
    pad = tk.StringVar(popup, value="7")
    ttk.Combobox(choices, textvariable=kind, state="readonly", width=20,
                 values=("Starport", "Fleet carrier", "Squadron carrier", "Colonisation ship")).grid(row=0, column=0)
    ttk.Spinbox(choices, from_=1, to=45, textvariable=pad, width=5).grid(row=0, column=1, padx=6)
    view = DockingView(popup); view.pack(fill="both", expand=True, padx=8, pady=8)
    view.preview = True
    if 'three_d' in _prefs:
        view.options['three_d'] = bool(_prefs['three_d'].get())
    if config.get_int("theme", default=0):
        view.configure(background="#101010")   # render() reads this before the popup is styled
    # Interface styles this popup (it opens from Settings). The diagram keeps its own fonts
    # and colours: mark the view's widgets so that pass does not repaint them.
    pending = list(view.winfo_children())
    while pending:
        widget = pending.pop()
        widget.navigator_color_preview = True
        pending.extend(widget.winfo_children())

    def show(denied=False):
        model = DockingState()
        station_type, name = {"Starport": ("Coriolis", "Preview starport"),
                              "Fleet carrier": ("FleetCarrier", "ABC-123"),
                              "Squadron carrier": ("FleetCarrier", "ABCD"),
                              "Colonisation ship": ("ColonisationShip", "Preview colonisation ship")}[kind.get()]
        model.handle({"event": "DockingDenied" if denied else "DockingGranted", "StationName": name,
                      "StationType": station_type, "LandingPad": pad.get(), "Reason": "NoSpace"})
        options = _settings()
        # Preview pending settings without changing live data or saved config.
        for key in ("hints", "reverse"):
            if key in _prefs:
                options[key] = bool(_prefs[key].get())
        try:
            options["size"] = max(180, min(480, int(_prefs["size"].get())))
        except (KeyError, ValueError, TypeError):
            pass
        options["diagram"] = True
        options['three_d'] = view.options['three_d']
        view.render(model, options)
        if not denied:
            view._stage('pad')
    ttk.Button(choices, text="Show Pad", command=show).grid(row=1, column=0, pady=6)
    ttk.Button(choices, text="Show Denial", command=lambda: show(True)).grid(row=1, column=1)
    show()


def plugin_prefs(parent, cmdr, is_beta):
    options = _settings()
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
    Entry = getattr(nb, "Entry", ttk.Entry)
    for key in BOOL_PREFS:
        _prefs[key] = tk.BooleanVar(frame, value=options[key])
    for key in ("size", "seconds"):
        _prefs[key] = tk.StringVar(frame, value=str(options[key]))
    nb.Label(frame, text=f"{TITLE} {VERSION}").grid(row=0, columnspan=2, sticky="w", padx=10, pady=10)
    row = 1
    for key, text in (("auto_show", "Hide Docking when not docking (show near stations)"),
                      ("denial_alert", "While hidden, still show docking denials (warning only, e.g. too far away)"),
                      ("diagram", "Show pad diagram when docking is granted"),
                      ("hints", "Show suggested next steps and guidance"),
                      ("reverse", "Green lights on left / rotate carrier diagram 180°"),
                      ("three_d", "Use 3D by default (also switchable on the panel)"),
                      ("auto_pad", "Switch to pad view on clearance (not entrance detection)"),
                      ("collapse_others", "Minimize other panels while docking")):
        nb.Checkbutton(frame, text=text, variable=_prefs[key]).grid(row=row, columnspan=2, sticky="w", padx=10)
        row += 1
    nb.Label(frame, text="Diagram size (180–480 px)").grid(row=row, column=0, sticky="w", padx=10, pady=6)
    Entry(frame, textvariable=_prefs["size"], width=6).grid(row=row, column=1, sticky="w")
    nb.Label(frame, text="Denial / timeout display (5–60 seconds)").grid(row=row + 1, column=0, sticky="w", padx=10, pady=6)
    Entry(frame, textvariable=_prefs["seconds"], width=6).grid(row=row + 1, column=1, sticky="w")
    ttk.Button(frame, text="Preview Diagrams and Denial Message…", command=lambda: _preview(frame)).grid(
        row=row + 2, columnspan=2, sticky="w", padx=10, pady=10)
    nb.Label(frame, text="Idle display stays compact. Pad guidance clears when you dock or leave.\n"
                        "Unsupported layouts still show your assigned pad number.\n"
                        "Reference models: no live ship/station position or entrance detection.\n"
                        "Drag a 3D view to orbit; select Entrance or Pad on the panel.").grid(
        row=row + 3, columnspan=2, sticky="w", padx=10, pady=6)
    # Required Interface owns the shared contrast preference and rendering (accessibility, above credits).
    try:
        from plug import invoke
        invoke("(N) Interface", "Navigator Interface", "navigator_background_preferences",
               frame, "Navigator_Docking")
    except ImportError:
        pass
    nb.Label(frame, text="Navigator suite plugin · Commander Thalinor\nOriginal wireframe artwork; pad-index reference credited in README.").grid(
        row=frame.grid_size()[1], columnspan=2, sticky="w", padx=10, pady=10)
    return outer


def prefs_changed(cmdr, is_beta):
    if not _prefs:
        return
    was_collapse = _settings()["collapse_others"]
    for key in BOOL_PREFS:
        suffix = {'three_d': 'ThreeD', 'auto_pad': 'AutoPad', 'auto_show': 'AutoShow', 'collapse_others': 'CollapseOthers',
                  'denial_alert': 'DenialAlert'}.get(key, key.title())
        config.set(PREFIX + suffix, bool(_prefs[key].get()))
    if not _settings()["denial_alert"] or not _settings()["auto_show"]:
        _end_alert()
    if was_collapse and not _settings()["collapse_others"]:
        _restore_other_panels()
    elif not was_collapse and _settings()["collapse_others"] and _active:
        _collapse_other_panels()
    _set_panel_visible(_active or _alert or not _settings()["auto_show"])
    for key, low, high, default in (("size", 180, 480, 320), ("seconds", 5, 60, 15)):
        try:
            value = int(_prefs[key].get())
        except (ValueError, TypeError):
            value = default
        config.set(PREFIX + key.title(), max(low, min(high, value)))
    _arm_expiry()
    _schedule()
