# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Choose a binding from the active preset and configure a macro step."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox
from .bindings import PROFILES
from .commands import defaults, new_macro, validate
from .editor import tree, buttons
from .ui import attach_window

class StepEditor(tk.Toplevel):
    def __init__(self, parent, step, on_save):
        super().__init__(parent)
        self.app, self.parent, self.on_save = parent.app, parent, on_save
        self.title("Choose Elite Action")
        self.navigator_window_id = "Voice_Navigator:binding_picker"
        self.geometry("818x653")
        self.minsize(770, 450)
        self.transient(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        step = copy.deepcopy(step or {"type": "action", "binding": "ship:LandingGearToggle"})
        self.profile = tk.StringVar(self, value=step["binding"].split(":", 1)[0])
        self.query = tk.StringVar(self)
        self.hold = tk.StringVar(self, value=str(step.get("hold", .09)))
        self.gap = tk.StringVar(self, value=str(step.get("gap", .15)))
        self.repeat = tk.StringVar(self, value=str(step.get("repeat", 1)))
        self.desired = tk.StringVar(self, value="Toggle / Press" if step.get("desired") is None else
                                   ("Ensure On / Deployed" if step["desired"] else "Ensure Off / Retracted"))
        ttk.Label(self, text="Preset section").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        box = ttk.Combobox(self, textvariable=self.profile, values=PROFILES, state="readonly", width=12)
        box.grid(row=0, column=1, sticky="w")
        box.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        ttk.Label(self, text="Find action").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ttk.Entry(self, textvariable=self.query).grid(row=1, column=1, sticky="ew", padx=(0, 12))
        self.query.trace_add("write", lambda *_: self.refresh())
        frame, self.table = tree(self, {"key": "Keyboard Binding", "tag": "Elite Action ID"},
                                {"#0": 250, "key": 240, "tag": 290})
        frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=8)
        options = ttk.Frame(self)
        options.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=6)
        for label, var in (("Hold (s)", self.hold), ("Gap (s)", self.gap), ("Repeat", self.repeat)):
            ttk.Label(options, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(options, textvariable=var, width=6).pack(side="left", padx=(0, 10))
        ttk.Combobox(options, textvariable=self.desired, values=(
            "Toggle / Press", "Ensure On / Deployed", "Ensure Off / Retracted"),
            state="readonly", width=23).pack(side="left")
        ttk.Label(self, text="Hold time supports 0.02 to 10 seconds. Ensure state supports landing gear, hardpoints, ship lights, cargo scoop and night vision.",
                  wraplength=790).grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=6)
        buttons(self, [("Use Action", self.save), ("Cancel", self.close)]
                ).grid(row=5, column=0, columnspan=2, sticky="e", padx=12, pady=10)
        self.refresh()
        if self.table.exists(step["binding"]):
            self.table.selection_set(step["binding"])
            self.table.see(step["binding"])
        self.protocol("WM_DELETE_WINDOW", self.close)
        attach_window(self, self.app)
        self.grab_set()
    def refresh(self):
        self.table.delete(*self.table.get_children())
        for binding in self.app.catalog.rows(self.profile.get(), self.query.get()):
            self.table.insert("", "end", iid=binding.identifier, text=binding.label,
                              values=(binding.display, binding.action))
    def save(self):
        selected = self.table.selection()
        if not selected:
            return
        try:
            binding = self.app.catalog.resolve(selected[0])
            step = {"type": "action", "binding": binding.identifier,
                    "hold": float(self.hold.get()), "gap": float(self.gap.get()),
                    "repeat": float(self.repeat.get())}
            if self.desired.get() != "Toggle / Press":
                step["desired"] = self.desired.get() == "Ensure On / Deployed"
            trial = defaults()
            trial["macros"] = [new_macro("Step", ["step"])]
            trial["macros"][0]["steps"] = [step]
            validate(trial)
            step["repeat"] = int(step["repeat"])
            self.on_save(step)
        except (ValueError, OSError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
            return
        self.close()
    def close(self):
        self.destroy()
        if self.parent.winfo_exists():
            self.parent.grab_set()
