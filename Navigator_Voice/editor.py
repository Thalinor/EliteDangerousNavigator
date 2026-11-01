# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Native editor for spoken aliases, ordered binding actions, and pauses."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from .bindings import PROFILES, PROFILE_NAMES, default_bindings_dir
from .commands import CONTEXTS, defaults, new_macro, validate
from .ui import attach_window
from .backups import backup_folder, write_backup, restore_candidate, move_backups

def tree(parent, columns, widths):
    frame = ttk.Frame(parent)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    table = ttk.Treeview(frame, columns=tuple(columns), show="tree headings", selectmode="browse")
    for key, label in [("#0", "Name")] + list(columns.items()):
        table.heading(key, text=label)
        table.column(key, width=widths.get(key, 150), minwidth=65)
    table.grid(row=0, column=0, sticky="nsew")
    bar = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
    bar.grid(row=0, column=1, sticky="ns")
    table.configure(yscrollcommand=bar.set)
    return frame, table

def buttons(parent, definitions):
    row = ttk.Frame(parent)
    for label, command in definitions:
        ttk.Button(row, text=label, command=command).pack(side="left", padx=(0, 5))
    return row

class MacroManager(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.frame.winfo_toplevel())
        self.app = app
        self.title("(N) Voice - Settings")
        self.navigator_window_id = "Voice_Navigator:macros"
        self.geometry("1112x918")
        self.minsize(780, 540)
        self.transient(app.frame.winfo_toplevel())
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        pages = {}
        for label in ("Voice Macros", "Elite Bindings", "Listening Settings", "TTS Settings", "Assistant", "Backup", "Activity Log"):
            page = ttk.Frame(notebook, padding=10)
            notebook.add(page, text=label)
            page.columnconfigure(0, weight=1)
            pages[label] = page
        page = pages["Voice Macros"]
        page.rowconfigure(0, weight=1)
        frame, self.table = tree(page, {"phrases": "Spoken Phrases", "context": "Context", "keys": "Bindings"},
                                {"#0": 200, "phrases": 320, "context": 85, "keys": 150})
        frame.grid(row=0, column=0, sticky="nsew")
        self.table.bind("<Double-1>", lambda _: self.edit())
        buttons(page, [("Add", self.add), ("Edit", self.edit), ("Duplicate", self.duplicate),
                       ("Remove", self.remove), ("Preview", self.preview)]).grid(row=1, column=0, sticky="w", pady=8)
        ttk.Label(page, text="Preview logs the steps without sending keys. Say 'cancel macro' to cancel a running sequence.",
                  wraplength=830).grid(row=2, column=0, sticky="w")
        page = pages["Elite Bindings"]
        page.rowconfigure(3, weight=1)
        filters = ttk.Frame(page)
        filters.grid(row=0, column=0, sticky="ew")
        self.profile, self.search = tk.StringVar(self, value="ship"), tk.StringVar(self)
        profile = ttk.Combobox(filters, textvariable=self.profile, values=PROFILES, state="readonly", width=10)
        profile.pack(side="left")
        profile.bind("<<ComboboxSelected>>", lambda _: self.refresh_bindings())
        ttk.Entry(filters, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=8)
        self.search.trace_add("write", lambda *_: self.refresh_bindings())
        buttons(page, [("Load Keybinding File…", self.load_bindings),
                       ("Clear All Keybindings", self.clear_bindings),
                       ("Default Keybindings", self.default_bindings)]).grid(row=1, column=0, sticky="w", pady=4)
        self.source = ttk.Label(page, wraplength=820)
        self.source.grid(row=2, column=0, sticky="w", pady=6)
        frame, self.actions = tree(page, {"key": "Keyboard Binding", "tag": "Elite Action ID"},
                                  {"#0": 260, "key": 250, "tag": 290})
        frame.grid(row=3, column=0, sticky="nsew")
        ttk.Button(page, text="Create Voice Macro from Selected Action", command=self.from_action).grid(row=4, column=0, sticky="w", pady=8)
        page = pages["Listening Settings"]
        page.columnconfigure(1, weight=1)
        self.wake = tk.StringVar(self, value=app.settings.get("wake_word", ""))
        self.ship_keyword_only = tk.BooleanVar(self, value=app.settings.get(
            'ship_keyword_only', bool(app.settings.get('wake_word', '').strip())))
        self.culture = tk.StringVar(self, value=app.settings.get("culture", ""))
        self.confidence = tk.StringVar(self, value=str(app.settings.get("confidence", .72)))
        self.override = tk.StringVar(self, value=app.settings.get("binds_override", ""))
        self.speak = tk.BooleanVar(self, value=app.settings.get("speak_replies", True))
        self.contrast = tk.BooleanVar(self, value=app.settings.get("high_contrast_background", False))
        for row, label, var in ((0, "Wake phrase (optional)", self.wake),
                (1, "Recognition language (blank = Windows default)", self.culture),
                (2, "Minimum confidence (0.10 to 1.00)", self.confidence)):
            if row == 0:
                label_widget = ttk.Checkbutton(page, text='Ship Inputs: Keyword Only', variable=self.ship_keyword_only)
            else:
                label_widget = ttk.Label(page, text=label)
            label_widget.grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
            ttk.Entry(page, textvariable=var).grid(row=row, column=1, sticky="ew", pady=7)
        ttk.Checkbutton(page, text="High Contrast Background", variable=self.contrast).grid(row=3, column=0, columnspan=2, sticky="w", pady=(15, 6))
        ttk.Checkbutton(page, text="Allow spoken replies for commands marked Spoken", variable=self.speak).grid(row=4, column=0, columnspan=2, sticky="w", pady=6)
        self.activity_log = tk.BooleanVar(self, value=app.settings.get("activity_log_enabled", True))
        ttk.Checkbutton(page, text="Enable Activity Log", variable=self.activity_log).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        self.listen_colors = tk.BooleanVar(self, value=app.settings.get("listen_status_colors", False))
        ttk.Checkbutton(page, text="Use red while listening and green while stopped", variable=self.listen_colors).grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(page, text="Recognition runs locally using Windows desktop speech components.\n"
                  "When Ship Inputs: Keyword Only is checked, precede each command with its keyword.\n"
                  "Built-in phrases: cancel macro; stop listening. These also use your wake phrase.\n"
                  "The microphone opens only when you click Listen. Check Speech Engine does not record audio.",
                  wraplength=820).grid(row=7, column=0, columnspan=2, sticky="w", pady=14)
        buttons(page, [("Save Settings", self.save_options), ("Check Speech Engine", app.check_engine)]
                ).grid(row=8, column=0, columnspan=2, sticky="w")
        page.rowconfigure(9, weight=1)
        ttk.Button(page, text="OK", command=lambda: self.save_options(close=True)).grid(
            row=10, column=0, columnspan=2, sticky="e", pady=(12, 0))
        page = pages["TTS Settings"]
        page.columnconfigure(1, weight=1)
        self.tts_voice = tk.StringVar(self, value=app.settings.get("tts_voice", "") or "Windows default")
        self.tts_rate = tk.IntVar(self, value=app.settings.get("tts_rate", 0))
        self.tts_pitch = tk.StringVar(self, value=app.settings.get("tts_pitch", "normal").title())
        self.tts_volume = tk.IntVar(self, value=app.settings.get("tts_volume", 100))
        ttk.Label(page, text="Installed Windows TTS voice").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=8)
        self.tts_voice_box = ttk.Combobox(page, textvariable=self.tts_voice,
            values=["Windows default"], state="readonly")
        self.tts_voice_box.grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Button(page, text="Check Installed Voices", command=app.check_engine).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(page, text="Speaking rate (-10 slow to +10 fast)").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Scale(page, from_=-10, to=10, variable=self.tts_rate, orient="horizontal").grid(row=1, column=1, sticky="ew", pady=8)
        ttk.Label(page, textvariable=self.tts_rate, width=4).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(page, text="Pitch").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Combobox(page, textvariable=self.tts_pitch, values=("Low", "Normal", "High"),
                     state="readonly", width=12).grid(row=2, column=1, sticky="w", pady=8)
        ttk.Label(page, text="Volume").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=8)
        ttk.Scale(page, from_=0, to=100, variable=self.tts_volume, orient="horizontal").grid(row=3, column=1, sticky="ew", pady=8)
        ttk.Label(page, textvariable=self.tts_volume, width=4).grid(row=3, column=2, padx=(8, 0))
        ttk.Label(page, text="Tone and voice quality come from the selected installed Windows voice.\n"
                  "Available voices depend on Windows. Pitch uses speech markup and may vary by voice.",
                  wraplength=800).grid(row=4, column=0, columnspan=3, sticky="w", pady=14)
        buttons(page, [("Save TTS Settings", self.save_tts), ("Preview Voice", self.preview_tts),
                       ("Reset Voice Defaults", self.reset_tts)]).grid(row=5, column=0, columnspan=3, sticky="w")
        page = pages["Assistant"]
        from .assistant_ui import AssistantPage
        self.assistant_page = AssistantPage(self, page)
        self.build_backup_page(pages["Backup"])
        page = pages["Activity Log"]
        page.rowconfigure(0, weight=1)
        self.logbox = tk.Text(page, wrap="word", state="disabled", height=12)
        self.logbox.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(page, orient="vertical", command=self.logbox.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.logbox.configure(yscrollcommand=bar.set)
        ttk.Button(page, text="Copy Log", command=self.copy_log).grid(row=1, column=0, sticky="w", pady=6)
        for line in app.logs:
            self.append_log(line)
        self.refresh()
        attach_window(self, app)
    def append_log(self, line):
        self.logbox.configure(state="normal")
        self.logbox.insert("end", line + "\n")
        lines = int(self.logbox.index("end-1c").split(".")[0])
        if lines > 251:
            self.logbox.delete("1.0", str(lines - 250) + ".0")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")
    def refresh(self):
        selection = self.table.selection()
        self.table.delete(*self.table.get_children())
        for macro in self.app.settings["macros"]:
            ready = True
            for step in macro["steps"]:
                if step["type"] == "action":
                    try:
                        self.app.catalog.resolve(step["binding"])
                    except ValueError:
                        ready = False
            self.table.insert("", "end", iid=macro["id"],
                text=macro["name"] + ("" if macro.get("enabled", True) else " [Disabled]"),
                values=("; ".join(macro["phrases"]), macro.get("context", "any"),
                        "Ready" if ready else "Needs keyboard binding"))
        if selection and self.table.exists(selection[0]):
            self.table.selection_set(selection[0])
        self.refresh_bindings()
    def refresh_bindings(self):
        self.actions.delete(*self.actions.get_children())
        source = ("All keybindings cleared in (N) Voice; Elite files were not changed."
                  if self.app.settings.get("bindings_cleared", False)
                  else self.app.catalog.sources.get(self.profile.get(), "No selected preset found"))
        warnings = " | ".join(self.app.catalog.warnings)
        self.source.configure(text=source + ("\n" + warnings if warnings else ""))
        for binding in self.app.catalog.rows(self.profile.get(), self.search.get()):
            self.actions.insert("", "end", iid=binding.identifier, text=binding.label,
                                values=(binding.display, binding.action))
    def selected(self):
        selection = self.table.selection()
        return next((m for m in self.app.settings["macros"] if selection and m["id"] == selection[0]), None)
    def commit_macro(self, macro):
        settings = copy.deepcopy(self.app.settings)
        index = next((i for i, m in enumerate(settings["macros"]) if m["id"] == macro["id"]), None)
        if index is None:
            settings["macros"].append(macro)
        else:
            settings["macros"][index] = macro
        self.app.apply_settings(settings)
        self.table.selection_set(macro["id"])
    def add(self):
        MacroEditor(self, new_macro("New macro", ["new command"]), self.commit_macro)
    def edit(self):
        macro = self.selected()
        if macro:
            MacroEditor(self, copy.deepcopy(macro), self.commit_macro)
    def duplicate(self):
        macro = self.selected()
        if macro:
            clone = copy.deepcopy(macro)
            clone.update(id=new_macro("", [])["id"], name=macro["name"] + " copy", enabled=False)
            MacroEditor(self, clone, self.commit_macro)
    def remove(self):
        macro = self.selected()
        if macro and messagebox.askyesno("Remove Macro", "Remove '" + macro["name"] + "'?", parent=self):
            settings = copy.deepcopy(self.app.settings)
            settings["macros"] = [m for m in settings["macros"] if m["id"] != macro["id"]]
            try:
                self.app.apply_settings(settings)
            except (OSError, ValueError) as error:
                messagebox.showerror("(N) Voice", str(error), parent=self)
    def preview(self):
        macro = self.selected()
        if macro:
            self.app.preview(macro)
    def reload(self):
        self.app.reload_bindings()
        self.refresh()
    def load_bindings(self):
        directory = default_bindings_dir()
        path = filedialog.askopenfilename(parent=self, title="Load Elite keybinding file",
            initialdir=str(directory) if directory.is_dir() else str(Path.home()),
            filetypes=[("Elite Dangerous keybindings", "*.binds")])
        if not path:
            return
        self._save_binding_source(path, False)
    def clear_bindings(self):
        if not messagebox.askyesno("Clear All Keybindings",
                "Clear all keybindings from (N) Voice? Saved Elite .binds files will not be changed.\n\n"
                "Voice commands that use bindings will show as needing a keyboard binding until you load or restore them.",
                icon="warning", parent=self):
            return
        self._save_binding_source(self.app.settings.get("binds_override", ""), True)
    def default_bindings(self):
        self._save_binding_source("", False)
    def _save_binding_source(self, path, cleared):
        settings = copy.deepcopy(self.app.settings)
        settings.update(binds_override=path, bindings_cleared=cleared)
        try:
            self.app.apply_settings(settings)
            self.override.set(path)
            self.refresh()
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
    def from_action(self):
        selected = self.actions.selection()
        if selected:
            binding = self.app.catalog.bindings[selected[0]]
            macro = new_macro(binding.label, [binding.label.lower()], binding.identifier)
            macro["context"] = binding.profile if binding.profile in CONTEXTS else "any"
            MacroEditor(self, macro, self.commit_macro)
    def choose_override(self):
        path = filedialog.askopenfilename(parent=self, title="Choose Elite bindings", filetypes=[("Elite bindings", "*.binds")])
        if path:
            self.override.set(path)
    def save_options(self, close=False):
        settings = copy.deepcopy(self.app.settings)
        try:
            settings.update(wake_word=self.wake.get().strip(), culture=self.culture.get().strip(),
                confidence=float(self.confidence.get()), binds_override=self.override.get().strip(),
                high_contrast_background=self.contrast.get(), speak_replies=self.speak.get(),
                activity_log_enabled=self.activity_log.get(),
                listen_status_colors=self.listen_colors.get())
            settings['ship_keyword_only'] = self.assistant_page.ship_only.get()
            self.app.apply_settings(settings)
            self.app.log("Listening settings saved")
            if close:
                self.destroy()
        except (ValueError, OSError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
    def build_backup_page(self, page):
        for column in (0, 1):
            page.columnconfigure(column, weight=1, uniform='voicebackup')
        ttk.Label(page, text="Back up your saved settings and commands.", wraplength=650).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        for row, label, kind in ((1, "Backup Plugin Settings", "settings"),
                                  (2, "Backup Voice Macros", "macros")):
            ttk.Button(page, text=label, command=lambda k=kind: self.make_backup(k)).grid(
                row=row, column=0, sticky="ew", pady=4)
        ttk.Button(page, text="Backup Assistant Settings", command=lambda: self.make_backup('assistant')).grid(
            row=3, column=0, sticky="ew", pady=4)
        ttk.Label(page, text="Assistant options and connections; API keys remain in Windows Credential Manager.", wraplength=280).grid(
            row=3, column=1, sticky="w", padx=(12, 0))
        ttk.Button(page, text="Backup Everything Together", command=lambda: self.make_backup("everything")).grid(
            row=4, column=0, sticky="ew", pady=4)
        ttk.Label(page, text="One file for a complete restore of saved plugin settings and voice macros.",
                  wraplength=280).grid(row=4, column=1, sticky="w", padx=(12, 0))
        self.backup_path = tk.StringVar(self, value=str(self.current_backup_folder()))
        ttk.Label(page, text="Backup folder").grid(row=5, column=0, sticky="w", pady=(16, 4))
        ttk.Entry(page, textvariable=self.backup_path, state="readonly").grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        for row, column, label, command in ((7, 0, "Choose Backup Folder…", self.choose_backup_folder),
                (7, 1, "Open Backup Folder", self.open_backup_folder),
                (8, 0, "Move Backup Folder…", self.move_backup_folder),
                (8, 1, "Load a Backup…", self.load_backup)):
            ttk.Button(page, text=label, command=command).grid(
                row=row, column=column, sticky="ew", padx=(0, 6), pady=4)
        self.backup_status = tk.StringVar(self, value="Backups use distinct filenames and never overwrite earlier backups.")
        ttk.Label(page, textvariable=self.backup_status, wraplength=650).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(12, 0))
    def current_backup_folder(self):
        return backup_folder(self.app.folder, self.app.settings)
    def make_backup(self, kind):
        try:
            path = write_backup(self.current_backup_folder(), kind, self.app.settings)
            self.backup_status.set("Saved " + path.name)
            self.app.log("Backup saved: " + str(path))
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice Backup", str(error), parent=self)
    def set_backup_folder(self, folder):
        settings = copy.deepcopy(self.app.settings)
        settings['backup_directory'] = str(folder)
        self.app.persist(settings)
        self.backup_path.set(str(folder))
    def choose_backup_folder(self):
        selected = filedialog.askdirectory(parent=self, title="Choose Backup Folder",
            initialdir=str(self.current_backup_folder()), mustexist=True)
        if selected:
            try:
                self.set_backup_folder(Path(selected))
                self.backup_status.set("Backup folder changed. Existing backups remain in their original folder.")
            except (OSError, ValueError) as error:
                messagebox.showerror("(N) Voice Backup", str(error), parent=self)
    def open_backup_folder(self):
        try:
            folder = self.current_backup_folder()
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except OSError as error:
            messagebox.showerror("(N) Voice Backup", str(error), parent=self)
    def move_backup_folder(self):
        selected = filedialog.askdirectory(parent=self, title="Move backups to this folder",
            initialdir=str(self.current_backup_folder()), mustexist=True)
        if not selected:
            return
        source, target = self.current_backup_folder().resolve(), Path(selected).resolve()
        if source == target:
            return
        try:
            moved = move_backups(source, target)
            try:
                self.set_backup_folder(target)
            except (OSError, ValueError):
                # Restore only the entries moved here, preserving other destination files.
                import shutil
                for name in reversed(moved):
                    shutil.move(str(target / name), str(source / name))
                raise
            self.backup_status.set("Backups moved to " + str(target) + ". Other files were left in place.")
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice Backup", str(error), parent=self)
    def load_backup(self):
        path = filedialog.askopenfilename(parent=self, title="Load (N) Voice Backup",
            initialdir=str(self.current_backup_folder()), filetypes=[("JSON backups", "*.json")])
        if not path:
            return
        try:
            kind, settings = restore_candidate(Path(path), self.app.settings)
            scope = {"settings": "plugin settings (your macros stay as they are)",
                     "macros": "voice macros (your other settings stay as they are)",
                     "assistant": "Assistant settings (API keys stay in Windows Credential Manager)",
                     "everything": "all saved plugin settings and voice macros"}[kind]
            if not messagebox.askyesno("Load Backup", "Restore " + scope + "?\n\n"
                    "A complete backup of your current saved setup will be made first.", parent=self):
                return
            previous = write_backup(self.current_backup_folder(), 'everything', self.app.settings)
            self.app.stop_listening()
            self.app.apply_settings(settings)
            for var, key, default in ((self.wake, "wake_word", ""), (self.culture, "culture", ""),
                    (self.confidence, "confidence", .72), (self.override, "binds_override", ""),
                    (self.contrast, "high_contrast_background", False), (self.speak, "speak_replies", True),
                    (self.activity_log, "activity_log_enabled", True)):
                var.set(settings.get(key, default))
            self.listen_colors.set(settings.get("listen_status_colors", False))
            self.assistant_page.reload()
            self.tts_voice.set(settings.get("tts_voice", "") or "Windows default")
            self.tts_rate.set(settings.get("tts_rate", 0))
            self.tts_pitch.set(settings.get("tts_pitch", "normal").title())
            self.tts_volume.set(settings.get("tts_volume", 100))
            self.backup_path.set(str(self.current_backup_folder()))
            self.backup_status.set("Restored " + Path(path).name + ". Previous setup: " + previous.name)
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append("\n".join(self.app.logs))
    def set_tts_voices(self, voices):
        names = sorted(set(v.get("name", "") for v in voices if v.get("name")))
        values = ["Windows default"] + names
        self.tts_voice_box.configure(values=values)
        current = self.tts_voice.get()
        if current not in values:
            self.tts_voice.set("Windows default")
    def tts_candidate(self):
        settings = copy.deepcopy(self.app.settings)
        settings.update(tts_voice="" if self.tts_voice.get() == "Windows default" else self.tts_voice.get(),
                        tts_rate=int(self.tts_rate.get()), tts_pitch=self.tts_pitch.get().lower(),
                        tts_volume=int(self.tts_volume.get()))
        return settings
    def save_tts(self):
        try:
            self.app.apply_settings(self.tts_candidate())
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
    def preview_tts(self):
        try:
            self.app.preview_tts(self.tts_candidate())
        except (OSError, ValueError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
    def reset_tts(self):
        self.tts_voice.set("Windows default")
        self.tts_rate.set(0)
        self.tts_pitch.set("Normal")
        self.tts_volume.set(100)
        self.save_tts()

class MacroEditor(tk.Toplevel):
    def __init__(self, parent, macro, on_save):
        super().__init__(parent)
        self.app, self.macro, self.on_save = parent.app, macro, on_save
        self.title("(N) Voice - Edit Macro")
        self.navigator_window_id = "Voice_Navigator:command_editor"
        self.geometry("1026x690")
        self.minsize(750, 500)
        self.transient(parent)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(6, weight=1)
        self.name = tk.StringVar(self, value=macro["name"])
        self.phrases = tk.StringVar(self, value="; ".join(macro["phrases"]))
        self.context = tk.StringVar(self, value=macro.get("context", "any"))
        self.enabled = tk.BooleanVar(self, value=macro.get("enabled", True))
        saved_reply = macro.get("reply", "")
        self._reply_is_default = not saved_reply or saved_reply == macro.get("name", "")
        self.reply = tk.StringVar(self, value=saved_reply or macro.get("name", ""))
        self.spoken = tk.BooleanVar(self, value=macro.get("speak_reply", False))
        def sync_default_reply(*_):
            if self._reply_is_default:
                self.reply.set(self.name.get())
        def note_custom_reply(*_):
            if self.reply.get() != self.name.get():
                self._reply_is_default = False
        self.name.trace_add("write", sync_default_reply)
        self.reply.trace_add("write", note_custom_reply)
        for row, label, var in ((0, "Macro name", self.name),
                (1, "Spoken phrases (separate with ;)", self.phrases), (3, "Spoken reply", self.reply)):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=7)
            ttk.Entry(self, textvariable=var).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(0, 12), pady=7)
        ttk.Label(self, text="Game context").grid(row=2, column=0, sticky="w", padx=12)
        ttk.Combobox(self, textvariable=self.context, values=CONTEXTS, state="readonly", width=12).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(self, text="Enabled", variable=self.enabled).grid(row=2, column=2, sticky="w", padx=12)
        ttk.Checkbutton(self, text="Spoken", variable=self.spoken).grid(row=4, column=0, sticky="w", padx=12)
        ttk.Label(self, text="Speak this reply after the macro completes successfully.",
                  wraplength=600).grid(row=4, column=1, columnspan=2, sticky="w", padx=(0, 12))
        ttk.Label(self, text="Steps run in order. Each action can use its own General, Ship, SRV, or On Foot preset.",
                  wraplength=800).grid(row=5, column=0, columnspan=3, sticky="w", padx=12, pady=8)
        frame, self.steps = tree(self, {"timing": "Timing / Repetitions"}, {"#0": 530, "timing": 240})
        frame.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=12)
        self.steps.bind("<Double-1>", lambda _: self.edit_step())
        buttons(self, [("Add Action", self.add_action), ("Add Pause", self.add_pause), ("Edit Step", self.edit_step),
            ("Remove", self.remove_step), ("Up", lambda: self.move(-1)), ("Down", lambda: self.move(1))]
            ).grid(row=7, column=0, columnspan=3, sticky="w", padx=12, pady=10)
        buttons(self, [("Save Macro", self.save), ("Cancel", self.destroy)]).grid(row=8, column=0, columnspan=3, sticky="e", padx=12, pady=(0, 12))
        self.refresh()
        attach_window(self, self.app)
        self.grab_set()
    def refresh(self, selected=None):
        self.steps.delete(*self.steps.get_children())
        for index, step in enumerate(self.macro["steps"]):
            if step["type"] == "wait":
                label, timing = "Pause", str(step["seconds"]) + " seconds"
            else:
                binding = self.app.catalog.bindings.get(step["binding"])
                label = (binding.label + " [" + PROFILE_NAMES[binding.profile] + "] -> " + binding.display) if binding else step["binding"]
                if step.get("desired") is not None:
                    label += " (ensure " + ("on/deployed" if step["desired"] else "off/retracted") + ")"
                timing = "%ss hold; %ss gap; x%s" % (step.get("hold", .09), step.get("gap", .15), step.get("repeat", 1))
            self.steps.insert("", "end", iid=str(index), text=label, values=(timing,))
        if selected is not None and self.steps.exists(str(selected)):
            self.steps.selection_set(str(selected))
    def index(self):
        selection = self.steps.selection()
        return int(selection[0]) if selection else None
    def set_step(self, index, step):
        if index is None:
            self.macro["steps"].append(step)
            index = len(self.macro["steps"]) - 1
        else:
            self.macro["steps"][index] = step
        self.refresh(index)
    def add_action(self):
        from .step_editor import StepEditor
        StepEditor(self, None, lambda step: self.set_step(None, step))
    def add_pause(self):
        seconds = simpledialog.askfloat("Add Pause", "Pause in seconds (0 to 30)", initialvalue=.5, minvalue=0, maxvalue=30, parent=self)
        if seconds is not None:
            self.set_step(None, {"type": "wait", "seconds": seconds})
    def edit_step(self):
        index = self.index()
        if index is None:
            return
        step = self.macro["steps"][index]
        if step["type"] == "wait":
            seconds = simpledialog.askfloat("Edit Pause", "Pause in seconds", initialvalue=step["seconds"], minvalue=0, maxvalue=30, parent=self)
            if seconds is not None:
                self.set_step(index, {"type": "wait", "seconds": seconds})
        else:
            from .step_editor import StepEditor
            StepEditor(self, step, lambda value: self.set_step(index, value))
    def remove_step(self):
        index = self.index()
        if index is not None:
            del self.macro["steps"][index]
            self.refresh(max(0, index - 1))
    def move(self, delta):
        index = self.index()
        if index is not None and 0 <= index + delta < len(self.macro["steps"]):
            steps = self.macro["steps"]
            steps[index], steps[index + delta] = steps[index + delta], steps[index]
            self.refresh(index + delta)
    def save(self):
        candidate = copy.deepcopy(self.macro)
        candidate.update(name=self.name.get().strip(),
            phrases=[p.strip() for p in self.phrases.get().split(";") if p.strip()],
            context=self.context.get(), enabled=self.enabled.get(), reply=self.reply.get().strip(),
            speak_reply=self.spoken.get())
        try:
            self.on_save(candidate)
        except (ValueError, OSError) as error:
            messagebox.showerror("(N) Voice", str(error), parent=self)
            return
        self.destroy()
