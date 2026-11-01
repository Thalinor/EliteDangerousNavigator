# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""The shared "train the galaxy-map clicks" window, opened from (N) Interface's settings.

One place for every plugin: the Galaxy Map key, and where the map's search box, first result and Plot
Route button (and the optional jet-cone controls) sit on screen. Trained once, shared by all plugins.
"""
from __future__ import annotations

import tkinter as tk
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, ttk
from typing import Any

import myNotebook as nb


class TrainingWindow:
    def __init__(self, engine: Any, owner: tk.Misc) -> None:
        self.engine = engine
        settings = owner.winfo_toplevel()
        window = self.window = tk.Toplevel(settings)
        window.title("Map shortcuts training")
        window.transient(settings)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = nb.Frame(window)
        frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        frame.columnconfigure(0, weight=1)
        self.frame = frame
        self.key_text = tk.StringVar()
        self.message = tk.StringVar(value="Start the game and sit at the cockpit view, then press a Train button.")
        self.point_text: dict[str, tk.StringVar] = {}
        self.buttons: list[ttk.Button] = []

        nb.Label(frame, text="Galaxy map key").grid(row=0, column=0, sticky=tk.W)
        nb.Label(frame, textvariable=self.key_text).grid(row=1, column=0, sticky=tk.W, padx=(12, 0))
        keys = nb.Frame(frame)
        keys.grid(row=2, column=0, sticky=tk.W, pady=(2, 10))
        self._button(keys, "Detect From Elite Bindings", self.detect).grid(row=0, column=0, padx=(0, 6))
        self._button(keys, "Load Keybindings…", self.load_binds).grid(row=0, column=1)

        self._group(3, "Routing clicks (search box, first result, Plot Route)", engine.ROUTING_STEPS,
                    "Train Routing Clicks", "Needed for putting a name into the galaxy map.")
        self._group(8, "Jet-cone clicks (optional)", engine.JETCONE_STEPS,
                    "Train Jet-Cone Clicks", "Only used by the jet-cone routing toggle.")

        nb.Label(frame, textvariable=self.message, wraplength=460, justify=tk.LEFT).grid(
            row=13, column=0, sticky=tk.W, pady=(12, 6))
        bottom = nb.Frame(frame)
        bottom.grid(row=14, column=0, sticky=tk.E)
        self._button(bottom, "Close", self.close, track=False).grid(row=0, column=0)
        self.refresh()
        try:
            from theme import theme
            theme.register(frame)
        except (ImportError, AttributeError, tk.TclError):
            pass
        window.after_idle(self._take_grab)
        # Suite rule: the window never gets smaller than what shows all of its buttons (Close included).
        window.update_idletasks()
        window.minsize(window.winfo_reqwidth(), window.winfo_reqheight())

    # ------------------------------------------------------------------ layout helpers
    def _button(self, parent: tk.Misc, text: str, command: Any, track: bool = True) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        if track:
            self.buttons.append(button)
        return button

    def _group(self, row: int, title: str, steps: tuple, button_text: str, note: str) -> None:
        nb.Label(self.frame, text=title).grid(row=row, column=0, sticky=tk.W, pady=(6, 0))
        nb.Label(self.frame, text=note).grid(row=row + 1, column=0, sticky=tk.W, padx=(12, 0))
        for index, (name, _label) in enumerate(steps):
            self.point_text[name] = tk.StringVar()
            nb.Label(self.frame, textvariable=self.point_text[name]).grid(
                row=row + 2 + index, column=0, sticky=tk.W, padx=(12, 0))
        self._button(self.frame, button_text, lambda s=steps: self.train(s)).grid(
            row=row + 2 + len(steps), column=0, sticky=tk.W, pady=(4, 0))

    def _take_grab(self) -> None:
        """EDMC's Settings window holds the input grab, so this window must take it (and give it back)."""
        try:
            settings = self.window.master
            self.window.lift()
            if settings.grab_current() is None:
                return              # opened from the main window: nothing is grabbing input
            self.window.grab_set()

            def give_back(event: Any) -> None:
                if event.widget is self.window:
                    try:
                        if settings.winfo_exists():
                            settings.grab_set()
                    except tk.TclError:
                        pass
            self.window.bind("<Destroy>", give_back, add="+")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ state
    def alive(self) -> bool:
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def refresh(self) -> None:
        if not self.alive():
            return
        engine = self.engine
        self.key_text.set(engine.settings.get("map_key_name") or "Not set")
        for name, label in engine.POINT_LABELS.items():
            if name in self.point_text:
                optional = name.startswith("jetcone")
                state = "trained" if engine.trained(name) else ("not trained (optional)" if optional else "not trained yet")
                self.point_text[name].set(f"{label}: {state}")

    def set_busy(self, busy: bool) -> None:
        for button in self.buttons:
            try:
                button.configure(state=tk.DISABLED if busy else tk.NORMAL)
            except tk.TclError:
                pass

    def status(self, text: str) -> None:
        if self.alive():
            self.message.set(text)

    # ------------------------------------------------------------------ actions
    def train(self, steps: tuple) -> None:
        self.set_busy(True)
        if not self.engine.start_training(steps, self.status, self.done):
            self.set_busy(False)

    def done(self, message: str) -> None:
        if self.alive():
            self.refresh()
            self.set_busy(False)
            self.message.set(message)

    def detect(self) -> None:
        name = self.engine.refresh_keybinding()
        self.message.set(f"Galaxy map key: {name}" if name else
                         "No keyboard key for the Galaxy Map was found in your Elite bindings.")
        self.refresh()

    def load_binds(self) -> None:
        import os
        base = self.engine.bindings_dir()
        path = filedialog.askopenfilename(
            title="Load Keybindings", parent=self.window,
            initialdir=base if os.path.isdir(base) else None,
            filetypes=(("Elite bindings", "*.binds"), ("All files", "*.*")))
        if not path:
            return
        try:
            name = self.engine.apply_binds(path)
        except (OSError, ET.ParseError) as error:
            messagebox.showerror("Load Keybindings", f"Could not read that file: {error}", parent=self.window)
            return
        if name is None:
            messagebox.showerror("Load Keybindings",
                                 "No keyboard binding for the Galaxy Map was found in that file.",
                                 parent=self.window)
            return
        self.engine.settings["binds_path"] = path
        self.engine.save()
        self.message.set(f"Galaxy map key: {name}")
        self.refresh()

    def close(self) -> None:
        if self.engine.training_active():
            self.engine.cancel_training()
        try:
            self.window.destroy()
        except tk.TclError:
            pass
