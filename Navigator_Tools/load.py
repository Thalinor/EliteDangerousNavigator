# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""(N) Tools - notes and a calculator for EDMC.

Part of the Navigator plugin suite by Commander Thalinor. Nothing here touches the game: it is a notepad and a calculator.
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import font as tkfont
from typing import Any

import myNotebook as nb
from config import appname, config

try:
    from . import calc
    from .notes import Notes
except ImportError:                      # loaded as a plain (non-package) plugin
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import calc
    from notes import Notes

TITLE = "(N) Tools"
HEADER_TITLE = "Tools"
VERSION = "0.2.1"
PREFIX = "NavTools_"
PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")
TABS = ("notes", "calc")
TAB_LABELS = {"notes": "Notes", "calc": "Calculator"}
COLLAPSE_UP, COLLAPSE_DOWN = "🔼", "🔽"   # standard EDMC plugin collapse button
BUTTON = {"pady": 0, "borderwidth": 1, "highlightthickness": 0, "cursor": "hand2"}   # same small buttons as the Dashboard
BUTTON_WIDTH = 7
KEY_WIDTH = 3
TAB_PAD_X = 8
SAVE_MS = 800                           # a note is saved this long after you stop typing
STATUS_MS = 2000                        # how long a notice such as "Saved" stays up
CONFIRM_MS = 3000                       # Delete must be tapped twice within this time
NOTE_LINES = 6
KEYS = (("C", "⌫", "%", "÷"), ("7", "8", "9", "×"), ("4", "5", "6", "−"),
        ("1", "2", "3", "+"), ("±", "0", ".", "="))
OPERATORS = "+−×÷%"

_ui: dict[str, Any] = {}
_root: tk.Misc | None = None
_stopped = True
_notes: Notes | None = None
_theme_pending = None
_theme_bindings: list[tuple[str, str]] = []
_after: dict[str, Any] = {}
_state = {"fresh": False, "error": False, "page_height": 0, "style": None, "tape": []}
TAPE_MAX = 60                           # sums kept on the calculator tape
TAPE_MIN_WIDTH = 100                    # pixels the tape needs beside the keypad; narrower than that it steps aside


# --------------------------------------------------------------------------- settings + files
def _get_bool(key: str, default: bool) -> bool:
    try:
        value = config.get_bool(PREFIX + key, default=default)
    except TypeError:
        value = config.get_bool(PREFIX + key)
    return default if value is None else bool(value)


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
    return os.path.join(base, "Navigator_Tools")


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


def _field_background() -> str:
    """Typing areas use the window's own colour, so in the Transparent theme they are see-through like everything else. That
    is safe: to click into one the pointer has to be over EDMC, and then the window turns solid (Navigator Interface)."""
    return _theme_colours()["background"]


# --------------------------------------------------------------------------- tabs and layout
def _current_tab() -> str:
    tab = _get_str("TabId", TABS[0])
    return tab if tab in TABS else TABS[0]


def _select_tab(name: str) -> None:
    _close_note_list()
    _save_notes()
    config.set(PREFIX + "TabId", name)
    _layout()


def _toggle_collapsed() -> None:
    _save_notes()
    config.set(PREFIX + "Collapsed", not _get_bool("Collapsed", False))
    _layout()


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
    """Every tab has the same height (the tallest), so EDMC's window does not jump when you switch tabs."""
    try:
        calculator = _ui["inners"]["calc"]
        modes = _ui["mode_labels"]["basic"].master
        calc_height = modes.winfo_reqheight() + 3 + max(_ui["basic"].winfo_reqheight(), _ui["game"].winfo_reqheight())
        wanted = max(_ui["inners"]["notes"].winfo_reqheight(), calc_height, calculator.winfo_reqheight())
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
        field = _field_background()
        normal, highlight = colours["foreground"], colours["highlight"]
        signature = (normal, highlight, field, colours["background"], _current_tab(), _ui["header"].cget("background"),
                     str(_ui["note_title"].cget("font")), str(_ui["header"].cget("font")))
        _fit_heights()
        _sync_tape()
        if signature == _state["style"]:
            return
        _state["style"] = signature
        reference = _ui["header"]
        for name in ("text", "display", "note_list", "calc_list", "tape"):
            widget = _ui.get(name)
            if widget is not None:
                widget.configure(background=field, foreground=normal, relief=tk.FLAT,
                                 highlightthickness=0 if name == "display" else 1,
                                 highlightbackground=colours["disabledforeground"],
                                 highlightcolor=highlight, font=reference.cget("font"))
                if name in ("text", "display"):
                    widget.configure(insertbackground=normal)
                if name == "tape":
                    widget.configure(foreground=highlight, selectbackground=field, selectforeground=highlight,
                                     inactiveselectbackground=field)
        border = colours["disabledforeground"]
        for name in ("side", "pad"):
            _ui[name].configure(background=field)
        _ui["side"].configure(highlightthickness=1, highlightbackground=border, highlightcolor=border)
        _ui["rule"].configure(background=border)
        for entry, _label, _var in _ui.get("fields", []):
            entry.configure(background=field, foreground=normal, insertbackground=normal, relief=tk.FLAT,
                            highlightthickness=1, highlightbackground=colours["disabledforeground"],
                            highlightcolor=highlight, font=reference.cget("font"))
        underlined = tkfont.Font(font=reference.cget("font"))
        underlined.configure(underline=True)
        _ui["underlined"] = underlined                               # keep the font alive while labels use it
        plain = reference.cget("font")
        for mode, label in _ui.get("mode_labels", {}).items():
            label.configure(foreground=highlight, font=underlined if mode == _get_str("CalcMode", "basic") else plain)
        for name in ("note_list", "calc_list"):
            _ui[name].configure(selectbackground=normal, selectforeground=field)
        small = tkfont.Font(font=reference.cget("font"))
        size = int(small.cget("size"))
        small.configure(size=size + 1 if size < 0 else max(6, size - 1))      # one point smaller, so it keeps clear of the box
        _ui["small_font"] = small
        for name in ("note_title", "calc_name"):
            _ui[name].configure(font=small)
        _equalise_buttons(highlight)
        _ui["calc_name"].configure(foreground=highlight)
        _draw_underlines(highlight)
        _fit_heights()
    except tk.TclError:
        pass


# --------------------------------------------------------------------------- notes
def _arrow_image(direction: str, side: int, colour: str) -> tk.PhotoImage:
    """A small solid triangle drawn pixel by pixel in the middle of a square image: it sits exactly in the centre of its
    button (the arrow characters of a font sit low, because fonts leave room for letters that hang below the line)."""
    image = tk.PhotoImage(width=side, height=side)
    height = max(5, round(side * 0.42) // 2 * 2 + 1)            # odd, so there is a middle row
    depth = (height + 1) // 2
    left = (side - depth) // 2
    top = (side - height) // 2
    half = (height - 1) / 2
    for row in range(height):
        length = max(1, round(depth * (1 - abs(row - half) / (half + 1))))
        start = left + depth - length if direction == "left" else left      # the point is at the left for "left"
        image.put(colour, to=(start, top + row, start + length, top + row + 1))
    return image


def _equalise_buttons(highlight: str = "#ff8000") -> None:
    """The bottom-row buttons all get the same height (the tallest lettered button). The arrow buttons are squares of that
    size with a drawn triangle in the exact middle."""
    buttons = [b for b in _ui.get("bottom_buttons", []) if b not in [a for a, _d in _ui.get("arrows", [])]]
    try:
        for button in buttons:
            button.configure(pady=0)
        tallest = max(button.winfo_reqheight() for button in buttons) if buttons else 0
        for button in buttons:
            extra = tallest - button.winfo_reqheight()
            if extra > 0:
                button.configure(pady=extra // 2)
        images = []
        for button, direction in _ui.get("arrows", []):
            edge = 2 * (int(float(button.cget("borderwidth"))) + int(float(button.cget("highlightthickness"))))
            side = max(7, tallest - edge)
            image = _arrow_image(direction, side, highlight)
            images.append(image)
            button.configure(image=image, text="", compound=tk.CENTER, width=side, height=side, padx=0, pady=0,
                             activebackground=button.cget("background"))
        _ui["arrow_images"] = images                              # keep them alive while the buttons use them
    except (tk.TclError, ValueError):
        pass


def _show_note() -> None:
    if _notes is None or "text" not in _ui:
        return
    _close_note_list()
    text = _ui["text"]
    text.delete("1.0", tk.END)
    text.insert("1.0", _notes.text)
    text.edit_modified(False)
    text.edit_reset()
    text.yview_moveto(0)
    _ui["note_title"].configure(text=_note_caption())
    _ui["status"].configure(text="")
    _cancel_delete_confirm()


def _note_modified(_event: Any = None) -> None:
    text = _ui["text"]
    if not text.edit_modified():
        return
    text.edit_modified(False)
    if _notes is None:
        return
    _notes.set_text(text.get("1.0", tk.END))
    _ui["note_title"].configure(text=_note_caption())
    _flash_status("")
    if _root is not None:
        if _after.get("save") is not None:
            _root.after_cancel(_after["save"])
        _after["save"] = _root.after(SAVE_MS, _save_notes)


def _flash_status(text: str) -> None:
    """A short notice under the buttons ('Saved'): it clears itself after a couple of seconds."""
    if "status" not in _ui or _root is None:
        return
    try:
        if _after.get("status") is not None:
            _root.after_cancel(_after["status"])
        _ui["status"].configure(text=text)
        _after["status"] = _root.after(STATUS_MS, lambda: _ui["status"].configure(text="")) if text else None
    except tk.TclError:
        pass


def _save_notes(announce: bool = True) -> None:
    if _root is not None and _after.get("save") is not None:
        try:
            _root.after_cancel(_after["save"])
        except tk.TclError:
            pass
    _after["save"] = None
    if _notes is None:
        return
    if "text" in _ui:
        try:
            _notes.set_text(_ui["text"].get("1.0", tk.END))
        except tk.TclError:
            pass
    saved = _notes.save()
    if announce and "status" in _ui:
        _flash_status("Saved" if saved else "Could not save")


def _note_caption() -> str:
    if len(_notes.items) == 1 and not _notes.items[0]["text"].strip():
        return "0 of 0 \u25be"                           # nothing written yet
    return f"{_notes.position()}  {_notes.title()} \u25be"


def _make_list(parent: tk.Misc) -> tk.Listbox:
    """A pick-list that opens inside the panel, in place of what is underneath (a pop-up menu is drawn by Windows outside
    EDMC's window and lands in the wrong place in EDMC's borderless themes)."""
    box = tk.Listbox(parent, height=NOTE_LINES, width=1, exportselection=False, activestyle="none", borderwidth=0,
                     takefocus=True, selectmode=tk.BROWSE, cursor="hand2")
    return box


def _close_note_list() -> None:
    box = _ui.get("note_list")
    if box is not None and box.winfo_manager():
        box.grid_remove()
        _ui["text"].grid()


def _go_to_note(index: int) -> None:
    if _notes is not None and index != _notes.current:
        _save_notes(announce=False)
        _notes.goto(index)
        _show_note()


def _pick_note_menu(_event: Any = None) -> None:
    """Tap the title: the note list opens where the text is; tap a note to go to it, or the title again to close it."""
    if _notes is None:
        return
    box = _ui["note_list"]
    if box.winfo_manager():
        _close_note_list()
        return
    _save_notes(announce=False)
    box.delete(0, tk.END)
    for index in range(len(_notes.items)):
        box.insert(tk.END, f"{index + 1}  {_notes.title(index)}")
    box.selection_set(_notes.current)
    box.see(_notes.current)
    _ui["text"].grid_remove()
    box.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(3, 8))
    _state["style"] = None
    _schedule_theme()


def _note_list_tapped(event: Any) -> None:
    box = _ui["note_list"]
    if box.size():
        index = box.nearest(event.y)
        _close_note_list()
        _go_to_note(index)


def _step(direction: int) -> None:
    if _notes is not None:
        _save_notes(announce=False)
        _notes.step(direction)
        _show_note()


def _new_note() -> None:
    if _notes is not None:
        _save_notes(announce=False)
        _notes.new()
        _show_note()
        _ui["text"].focus_set()


def _cancel_delete_confirm() -> None:
    if _root is not None and _after.get("confirm") is not None:
        try:
            _root.after_cancel(_after["confirm"])
        except tk.TclError:
            pass
    _after["confirm"] = None
    if "delete" in _ui:
        _ui["delete"].configure(text="Delete")


def _delete_note() -> None:
    """Delete needs a second tap (the button says 'Sure?'), so a stray touch never loses a note."""
    if _notes is None or _root is None:
        return
    if _after.get("confirm") is None:
        _ui["delete"].configure(text="Sure?")
        _after["confirm"] = _root.after(CONFIRM_MS, _cancel_delete_confirm)
        return
    _cancel_delete_confirm()
    _notes.delete()
    _notes.save()
    _show_note()
    _flash_status("Deleted")


# --------------------------------------------------------------------------- basic calculator
def _display() -> tk.Entry:
    return _ui["display"]


def _set_display(text: str) -> None:
    entry = _display()
    entry.delete(0, tk.END)
    entry.insert(0, text)
    entry.icursor(tk.END)


def _equals(_event: Any = None) -> str:
    text = _display().get()
    if not text.strip():
        return "break"
    try:
        result = calc.fmt_calc(calc.evaluate(text))
    except calc.CalcError:
        _set_display("Error")
        _state.update(error=True, fresh=True)
        return "break"
    _tape_add(text, result)
    _set_display(result)
    _state.update(error=False, fresh=True)
    return "break"


# --------------------------------------------------------------------------- the tape (history of sums)
def _tape_add(expression: str, result: str) -> None:
    tape = _state["tape"]
    tape.append((expression.strip(), result))
    del tape[:-TAPE_MAX]
    _render_tape()


def _render_tape() -> None:
    box = _ui.get("tape")
    if box is None:
        return
    try:
        box.configure(state=tk.NORMAL)
        box.delete("1.0", tk.END)
        for number, (expression, result) in enumerate(_state["tape"]):
            if number:
                box.insert(tk.END, "\n")
            box.insert(tk.END, f"{expression} = {result}", ("tape", f"e{number}"))
        box.configure(state=tk.DISABLED)
        box.see(tk.END)
    except tk.TclError:
        pass


def _tape_tapped(event: Any) -> None:
    """Tap a line on the tape and its result comes back into the display, ready to carry on from."""
    box = _ui["tape"]
    try:
        box.tag_remove(tk.SEL, "1.0", tk.END)
        for tag in box.tag_names(f"@{event.x},{event.y}"):
            if tag[:1] == "e" and tag[1:].isdigit() and int(tag[1:]) < len(_state["tape"]):
                _set_display(_state["tape"][int(tag[1:])][1])
                _state.update(fresh=True, error=False)
                return
    except tk.TclError:
        pass


def _sync_tape() -> None:
    """The tape steps aside when the panel is too narrow for it, so the keypad never gets squeezed."""
    box, basic, side = _ui.get("tape"), _ui.get("basic"), _ui.get("side")
    if box is None or basic is None or side is None:
        return
    try:
        width = basic.winfo_width()
        if width > 1:
            if width < side.winfo_reqwidth() + TAPE_MIN_WIDTH:
                if box.winfo_manager():
                    box.grid_remove()
            elif not box.winfo_manager():
                box.grid()
    except tk.TclError:
        pass


def _key(symbol: str) -> None:
    if symbol == "=":
        _equals()
        return
    if symbol == "C":
        if not _display().get() and not _state["error"]:
            _state["tape"].clear()                        # a second C, on an empty display, clears the tape
            _render_tape()
        _set_display("")
        _state.update(error=False, fresh=False)
        return
    if _state["error"]:
        _set_display("")
        _state.update(error=False, fresh=False)
    text = _display().get()
    if symbol == "⌫":
        _set_display("" if _state["fresh"] else text[:-1])
        _state["fresh"] = False
        return
    if symbol == "±":
        _set_display(text[1:] if text.startswith("-") else "-" + text if text else "")
        return
    if _state["fresh"] and symbol not in OPERATORS:
        text = ""                                     # a number typed after a result starts a new sum
    _state["fresh"] = False
    if symbol in OPERATORS and text and text[-1] in OPERATORS and symbol != "%":
        text = text[:-1]                              # a second operator replaces the first
    _set_display(text + symbol)


TYPED_OPERATORS = {"*": "×", "x": "×", "X": "×", "/": "÷", "-": "−"}      # what the keyboard types -> what the keypad shows


def _display_typed(event: Any) -> str | None:
    """Typing in the display with the keyboard counts as editing: a result no longer restarts the sum. The keyboard's
    * or x make a times, / a divide and - a minus, so the display looks the same however the sum was entered; = works out."""
    char = event.char
    if not char or not char.isprintable():
        return None
    if char == "=":
        return _equals()
    if _state["error"]:
        _set_display("")
    if char in TYPED_OPERATORS or char in "+%":
        _state.update(fresh=False, error=False)          # carry on from the result
        _display().insert(tk.INSERT, TYPED_OPERATORS.get(char, char))
        return "break"
    if _state["fresh"]:
        _set_display("")
    _state.update(fresh=False, error=False)
    return None


# --------------------------------------------------------------------------- game calculations
def _calc_names() -> list[str]:
    return [name for name, _fields, _compute in calc.GAME_CALCS]


def _calc_index() -> int:
    name = _get_str("CalcName", _calc_names()[0])
    names = _calc_names()
    return names.index(name) if name in names else 0


def _choose_calc(index: int) -> None:
    names = _calc_names()
    config.set(PREFIX + "CalcName", names[index % len(names)])
    _show_calc()


def _step_calc(direction: int) -> None:
    _choose_calc(_calc_index() + direction)


def _pick_calc_menu(_event: Any = None) -> None:
    """Tap the name: the list of calculations opens where the boxes are; tap one, or the name again to close it."""
    box = _ui["calc_list"]
    if box.winfo_manager():
        _show_calc()
        return
    box.delete(0, tk.END)
    for name in _calc_names():
        box.insert(tk.END, name)
    box.selection_set(_calc_index())
    for entry, label, _var in _ui["fields"]:
        entry.grid_remove()
        label.grid_remove()
    for caption, value in _ui["results"]:
        caption.grid_remove()
        value.grid_remove()
    box.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(3, 0))
    _state["style"] = None
    _schedule_theme()


def _calc_list_tapped(event: Any) -> None:
    box = _ui["calc_list"]
    if box.size():
        _choose_calc(box.nearest(event.y))


def _show_calc() -> None:
    if "calc_name" not in _ui:
        return
    name, fields, _compute = calc.GAME_CALCS[_calc_index()]
    _ui["calc_list"].grid_remove()
    _ui["calc_name"].configure(text=f"{name} ▾")
    for number_, (entry, label, var) in enumerate(_ui["fields"]):
        if number_ < len(fields):
            label.configure(text=fields[number_][1])
            label.grid()
            entry.grid()
        else:
            label.grid_remove()
            entry.grid_remove()
    _compute_game()


def _compute_game(*_args: Any) -> None:
    if "fields" not in _ui:
        return
    name, fields, _compute = calc.GAME_CALCS[_calc_index()]
    values = {fields[i][0]: var.get() for i, (_entry, _label, var) in enumerate(_ui["fields"]) if i < len(fields)}
    rows = calc.compute(name, values)
    for number_, (caption, value) in enumerate(_ui["results"]):
        if number_ < len(rows):
            caption.configure(text=rows[number_][0] + ":")
            value.configure(text=rows[number_][1])
            caption.grid()
            value.grid()
        else:
            caption.configure(text="")
            value.configure(text="")
            caption.grid_remove()
            value.grid_remove()


def _set_mode(mode: str) -> None:
    config.set(PREFIX + "CalcMode", mode)
    _show_mode()
    _state["style"] = None
    _schedule_theme()


def _show_mode() -> None:
    mode = _get_str("CalcMode", "basic")
    if mode == "game":
        _ui["basic"].grid_remove()
        _ui["game"].grid()
    else:
        _ui["game"].grid_remove()
        _ui["basic"].grid()


# --------------------------------------------------------------------------- building the panel
def plugin_start3(plugin_dir: str) -> str:
    global _notes
    _notes = Notes(os.path.join(_data_dir(), "notes.json"))
    logger.info("%s %s loaded", TITLE, VERSION)
    return TITLE


def _button(parent: tk.Misc, text: str, command: Any, width: int = BUTTON_WIDTH) -> tk.Button:
    return tk.Button(parent, text=text, width=width, command=command, **BUTTON)


def plugin_app(parent: tk.Frame) -> tk.Frame:
    global _root, _stopped
    _root = parent.winfo_toplevel()
    _stopped = False
    _state.update(page_height=0, style=None, fresh=False, error=False)
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
    tight = {"pady": 0, "borderwidth": 0}

    # ---- Notes
    notes = tk.Frame(pages["notes"])
    notes.place(x=0, y=0, relwidth=1, relheight=1)
    notes.columnconfigure(1, weight=1)
    _ui["inners"]["notes"] = notes
    # Tap the title for a list of every note (its title is the note's first line).
    _ui["note_title"] = tk.Label(notes, text="", anchor=tk.CENTER, cursor="hand2", takefocus=True, **tight)
    _ui["note_title"].grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=(0, 2))
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _ui["note_title"].bind(sequence, _pick_note_menu)
    text = tk.Text(notes, height=NOTE_LINES, width=1, wrap=tk.WORD, undo=True, takefocus=True, padx=3, pady=2)
    text.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(3, 8))        # room under the box so the buttons do not touch its border
    text.bind("<<Modified>>", _note_modified)
    text.bind("<FocusOut>", lambda _event: _save_notes(announce=False))
    _ui["text"] = text
    note_list = _make_list(notes)
    note_list.bind("<ButtonRelease-1>", _note_list_tapped)
    _ui["note_list"] = note_list
    # One bottom row: previous note at the left corner, New / Save / Delete in the middle, next note at the right corner.
    previous_note = _button(notes, "<", lambda: _step(-1), KEY_WIDTH)
    previous_note.grid(row=2, column=0, sticky=tk.W)
    buttons = tk.Frame(notes)
    buttons.grid(row=2, column=1)
    new_button = _button(buttons, "New", _new_note)
    new_button.grid(row=0, column=0, padx=3)
    save_button = _button(buttons, "Save", _save_notes)
    save_button.grid(row=0, column=1, padx=3)
    _ui["delete"] = _button(buttons, "Delete", _delete_note)
    _ui["delete"].grid(row=0, column=2, padx=3)
    next_note = _button(notes, ">", lambda: _step(1), KEY_WIDTH)
    next_note.grid(row=2, column=2, sticky=tk.E)
    _ui["bottom_buttons"] = [previous_note, new_button, save_button, _ui["delete"], next_note]
    _ui["arrows"] = [(previous_note, "left"), (next_note, "right")]
    _ui["status"] = tk.Label(notes, text="", anchor=tk.CENTER, **tight)
    _ui["status"].grid(row=3, column=0, columnspan=3, sticky=tk.EW)

    # ---- Calculator
    calculator = tk.Frame(pages["calc"])
    calculator.place(x=0, y=0, relwidth=1, relheight=1)
    calculator.columnconfigure(0, weight=1)
    _ui["inners"]["calc"] = calculator
    modes = tk.Frame(calculator)
    modes.grid(row=0, column=0)
    _ui["mode_labels"] = {}
    for column, (mode, caption) in enumerate((("basic", "Basic"), ("game", "Game"))):
        label = tk.Label(modes, text=caption, cursor="hand2", takefocus=True, **tight)
        label.grid(row=0, column=column, padx=8)
        for sequence in ("<Button-1>", "<Return>", "<space>"):
            label.bind(sequence, lambda _event, m=mode: _set_mode(m))
        _ui["mode_labels"][mode] = label

    basic = tk.Frame(calculator)
    basic.grid(row=1, column=0, sticky=tk.EW, pady=(6, 0))
    basic.columnconfigure(0, weight=1)                           # the tape takes whatever width the keypad leaves
    _ui["basic"] = basic
    tape = tk.Text(basic, width=1, height=1, wrap=tk.WORD, state=tk.DISABLED, cursor="hand2", takefocus=False,
                   borderwidth=0, padx=3, pady=2, exportselection=False)
    tape.tag_configure("tape", justify=tk.RIGHT)
    tape.bind("<ButtonRelease-1>", _tape_tapped)
    tape.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))      # as tall as the display and keypad beside it
    _ui["tape"] = tape
    side = tk.Frame(basic)                        # the calculator itself: one thin box round the display and the keys
    side.grid(row=0, column=1, sticky=tk.N)
    side.columnconfigure(0, weight=1)
    _ui["side"] = side
    display = tk.Entry(side, justify=tk.RIGHT, width=1)
    display.grid(row=0, column=0, sticky=tk.EW)
    _ui["rule"] = tk.Frame(side, height=1, borderwidth=0, highlightthickness=0)       # hairline under the display
    _ui["rule"].grid(row=1, column=0, sticky=tk.EW)
    display.bind("<Return>", _equals)
    display.bind("<KeyPress>", _display_typed, add="+")
    _ui["display"] = display
    pad = tk.Frame(side)
    pad.grid(row=2, column=0, pady=(2, 1))
    _ui["pad"] = pad
    for row, keys in enumerate(KEYS):
        for column, symbol in enumerate(keys):
            _button(pad, symbol, lambda s=symbol: _key(s), KEY_WIDTH).grid(row=row, column=column, padx=2, pady=1)

    game = tk.Frame(calculator)
    game.grid(row=1, column=0, sticky=tk.EW, pady=(6, 0))
    game.columnconfigure(1, weight=1)
    _ui["game"] = game
    chooser = tk.Frame(game)
    chooser.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
    chooser.columnconfigure(1, weight=1)
    calc_previous = _button(chooser, "<", lambda: _step_calc(-1), KEY_WIDTH)
    calc_previous.grid(row=0, column=0)
    _ui["calc_name"] = tk.Label(chooser, text="", cursor="hand2", takefocus=True, anchor=tk.CENTER, **tight)
    _ui["calc_name"].grid(row=0, column=1, sticky=tk.EW)
    for sequence in ("<Button-1>", "<Return>", "<space>"):
        _ui["calc_name"].bind(sequence, _pick_calc_menu)
    calc_next = _button(chooser, ">", lambda: _step_calc(1), KEY_WIDTH)
    calc_next.grid(row=0, column=2)
    _ui["arrows"] += [(calc_previous, "left"), (calc_next, "right")]
    _ui["calc_list"] = _make_list(game)
    _ui["calc_list"].configure(height=len(calc.GAME_CALCS))
    _ui["calc_list"].bind("<ButtonRelease-1>", _calc_list_tapped)
    _ui["fields"] = []
    for number_ in range(calc.MAX_FIELDS):
        label = tk.Label(game, text="", anchor=tk.W, **tight)
        label.grid(row=number_ + 1, column=0, sticky=tk.W, pady=1)
        var = tk.StringVar()
        var.trace_add("write", _compute_game)
        entry = tk.Entry(game, textvariable=var, width=1, justify=tk.RIGHT)
        entry.grid(row=number_ + 1, column=1, sticky=tk.EW, padx=(6, 0), pady=1)
        _ui["fields"].append((entry, label, var))
    _ui["results"] = []
    for number_ in range(calc.MAX_RESULTS):
        caption = tk.Label(game, text="", anchor=tk.W, **tight)
        caption.grid(row=calc.MAX_FIELDS + 1 + number_, column=0, sticky=tk.W)
        value = tk.Label(game, text="", anchor=tk.E, **tight)
        value.grid(row=calc.MAX_FIELDS + 1 + number_, column=1, sticky=tk.E)
        _ui["results"].append((caption, value))

    try:
        from theme import theme
        theme.register(text)
        theme.register(display)
        theme.register(tape)
        for entry, _label, _var in _ui["fields"]:
            theme.register(entry)
    except ImportError:
        pass

    _show_note()
    _show_calc()
    _show_mode()
    _layout()
    for sequence in ("<<ThemeChanged>>", "<<NavigatorGlass>>", "<Configure>", "<Map>"):
        _theme_bindings.append((sequence, _root.bind(sequence, _schedule_theme, add="+")))
    _schedule_theme()                     # EDMC applies its theme after plugin_app
    return frame


def plugin_stop() -> None:
    global _stopped, _theme_pending
    _save_notes(announce=False)
    _stopped = True
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


def plugin_prefs(parent: nb.Notebook, cmdr: str, is_beta: bool) -> tk.Frame:
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
    nb.Label(frame, text="Notes are saved automatically a moment after you stop typing, and when you leave the tab.").grid(
        row=1, column=0, sticky=tk.W, padx=10)
    nb.Label(frame, text="Notes file: " + os.path.join(_data_dir(), "notes.json")).grid(row=2, column=0, sticky=tk.W, padx=10)
    nb.Label(frame, text="The Calculator's Game tab does arithmetic on numbers you type; it reads nothing from the game.").grid(
        row=3, column=0, sticky=tk.W, padx=10, pady=(4, 0))
    return outer
