# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Saved EDMC colour schemes (Normal Text / Highlighted Text) for Settings.

Nothing is forced: Apply only fills EDMC's own Appearance colours in the open
Settings dialog, and EDMC saves them when the user presses OK. Changing colours
later in Appearance simply shows "Custom".
"""
import json
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import myNotebook as nb

CFG_SCHEMES = "NavInterface_ColorSchemes"     # JSON [[name, normal, highlighted], ...]
CFG_ORIGINAL = "NavInterface_ColorOriginal"   # first colours seen, kept as "My Original"
BUILT_IN = (("Elite Dangerous", "#b36804", "#efa201"),
            ("EDMC Default", "#ff8000", "#ffffff"))
ORIGINAL_NAME = "My Original"
MAX_NAME = 40


def _hex(widget, colour):
    try:
        red, green, blue = widget.winfo_rgb(str(colour))
    except tk.TclError:
        return str(colour).strip().lower()
    return "#%02x%02x%02x" % (red >> 8, green >> 8, blue >> 8)


class ColorSchemes:
    def __init__(self, config, logger):
        self.config, self.logger = config, logger

    def saved(self):
        try:
            rows = json.loads(self.config.get_str(CFG_SCHEMES, default="[]") or "[]")
        except (TypeError, ValueError):
            return []
        return [(str(r[0])[:MAX_NAME], str(r[1]), str(r[2])) for r in rows
                if isinstance(r, list) and len(r) == 3 and str(r[0]).strip()]

    def store(self, rows):
        self.config.set(CFG_SCHEMES, json.dumps([list(row) for row in rows]))

    def remember_original(self, widget):
        """Keep the colours a user had before ever using this, once."""
        if self.config.get_str(CFG_ORIGINAL, default=""):
            return
        current = (_hex(widget, self.config.get_str("dark_text", default="#ff8000") or "#ff8000"),
                   _hex(widget, self.config.get_str("dark_highlight", default="white") or "white"))
        self.config.set(CFG_ORIGINAL, json.dumps(list(current)))
        known = {(_hex(widget, a), _hex(widget, b)) for _, a, b in BUILT_IN + tuple(self.saved())}
        if current not in known:
            self.store(self.saved() + [(ORIGINAL_NAME,) + current])

    def all(self):
        return list(BUILT_IN) + self.saved()

    def build(self, frame, row, dark_only):
        """Add the section to Navigator Interface's settings page."""
        dialog = frame.winfo_toplevel()
        colours = getattr(dialog, "theme_colors", None)
        refresh = getattr(dialog, "themevarchanged", None)
        box = nb.Frame(frame)
        box.grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=10, pady=(14, 0))
        nb.Label(box, text="Colour scheme (EDMC Normal Text / Highlighted Text)").grid(
            row=1, column=0, columnspan=5, sticky=tk.W)
        if not isinstance(colours, list) or len(colours) < 2 or not callable(refresh):
            nb.Label(box, text="Not available in this EDMC version.").grid(row=2, column=0, sticky=tk.W)
            return
        try:
            self.remember_original(box)
        except Exception:
            self.logger.exception("Colour schemes: could not record the original colours")
        choice = tk.StringVar(master=box)
        picker = ttk.Combobox(box, textvariable=choice, state="readonly", width=24)
        picker.grid(row=2, column=0, sticky=tk.W, pady=(4, 0))
        status = nb.Label(box, text="")
        status.grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=(4, 0))

        def current_name():
            draft = (_hex(box, colours[0]), _hex(box, colours[1]))
            for name, normal, highlight in self.all():
                if (_hex(box, normal), _hex(box, highlight)) == draft:
                    return name
            return "Custom"

        def show(message=None):
            names = [name for name, _, _ in self.all()]
            picker.configure(values=names)
            current = current_name()
            if choice.get() not in names:
                choice.set(current if current in names else names[0])
            delete.configure(state=tk.NORMAL if choice.get() not in dict.fromkeys(n for n, _, _ in BUILT_IN)
                             and str(picker.cget("state")) != tk.DISABLED else tk.DISABLED)
            status.configure(text=message or f"Current colours: {current}")

        def apply():
            for name, normal, highlight in self.all():
                if name == choice.get():
                    colours[0], colours[1] = normal, highlight
                    refresh()              # EDMC's own preview; EDMC saves it on OK
                    show(f"{name} selected. Press OK to apply.")
                    return

        def save():
            name = simpledialog.askstring("Save colour scheme", "Name for the current colours:",
                                          parent=dialog)
            if name is None:
                return
            name = " ".join(name.split())[:MAX_NAME]
            if not name or name.casefold() in (n.casefold() for n, _, _ in BUILT_IN) or name == "Custom":
                messagebox.showinfo("Save colour scheme", "Please choose a different name.", parent=dialog)
                return
            rows = self.saved()
            if any(n.casefold() == name.casefold() for n, _, _ in rows):
                if not messagebox.askyesno("Save colour scheme", f"Replace '{name}'?", parent=dialog):
                    return
                rows = [r for r in rows if r[0].casefold() != name.casefold()]
            self.store(rows + [(name, _hex(box, colours[0]), _hex(box, colours[1]))])
            choice.set(name)
            show(f"Saved '{name}'.")

        def remove():
            name = choice.get()
            if name in (n for n, _, _ in BUILT_IN):
                return
            if messagebox.askyesno("Delete colour scheme", f"Delete '{name}'?", parent=dialog):
                self.store([r for r in self.saved() if r[0] != name])
                choice.set("")
                show()

        apply_button = ttk.Button(box, text="Apply", command=apply)
        apply_button.grid(row=2, column=1, padx=(6, 0), pady=(4, 0))
        save_button = ttk.Button(box, text="Save Current As…", command=save)
        save_button.grid(row=2, column=2, padx=(6, 0), pady=(4, 0))
        delete = ttk.Button(box, text="Delete", command=remove)
        delete.grid(row=2, column=3, padx=(6, 0), pady=(4, 0))
        picker.bind("<<ComboboxSelected>>", lambda _event: show(), add="+")
        box.bind("<Map>", lambda _event: show(), add="+")   # catches colours picked in Appearance
        dark_only.extend(((picker, "readonly"), (apply_button, tk.NORMAL), (save_button, tk.NORMAL)))
        dark_only.append((delete, None))   # None: state decided by show()
        self.show = show
        show()
