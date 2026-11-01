# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Shared main-panel contrast. Event driven, scoped to plugin panels."""
import tkinter as tk
from tkinter import ttk

FORCE = 'NavInterface_ForceHighContrastBackgrounds'
PREFIX = 'NavInterface_HighContrast_'


class PanelBackgrounds:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.records, self.drafts = {}, {}
        self.local = {}
        self.style = ttk.Style(root)
        self._style_signatures = {}

    def enabled(self, folder):
        return (self.config.get_bool(FORCE, default=False)
                or self.local.get(folder, self.config.get_bool(PREFIX + folder, default=False)))

    def preferences(self, page, folder=None):
        key = PREFIX + folder if folder else FORCE
        var = tk.BooleanVar(page, value=self.config.get_bool(key, default=False))
        text = 'High Contrast Background' if folder else 'Force High Contrast Backgrounds on All Plugins'
        box = ttk.Checkbutton(page, text=text, variable=var)
        row = page.grid_size()[1]
        box.grid(row=row, column=0, columnspan=max(1, page.grid_size()[0]), sticky='w', padx=10, pady=8)
        self.drafts[key] = (page, var)
        return box

    def save_preferences(self):
        for key, (page, var) in list(self.drafts.items()):
            try:
                if page.winfo_exists():
                    self.config.set(key, bool(var.get()))
                else:
                    self.drafts.pop(key, None)
            except tk.TclError:
                self.drafts.pop(key, None)

    def _readable(self, color):
        try:
            # Preserve orange, status colours and highlights; lift dark default text.
            return 'white' if max(self.root.winfo_rgb(color)) < 80 * 257 else color
        except tk.TclError:
            return color

    def _same(self, a, b):
        try:
            return self.root.winfo_rgb(a) == self.root.winfo_rgb(b)
        except tk.TclError:
            return str(a) == str(b)

    def _paint(self, widget, record):
        original = record['values']
        base = original.get('style') or widget.winfo_class()
        foreground = (self.style.lookup(base, 'foreground') or 'black') if record['ttk'] else None
        signature = (record['enabled'], tuple(original.items()),
                     self.style.theme_use() if record['ttk'] else None, foreground)
        if record.get('signature') == signature:
            return
        if record['ttk']:
            values = dict(original)
            if record['enabled']:
                target = 'NavContrast' + str(id(widget)) + '.' + base
                style_signature = (signature[2], self._readable(foreground))
                if self._style_signatures.get(target) != style_signature:
                    self.style.configure(target, background='black', fieldbackground='black',
                                         foreground=style_signature[1])
                    self._style_signatures[target] = style_signature
                record['forced_style'] = target
                values['style'] = target
                for key in values:
                    if key in ('background', 'activebackground', 'selectcolor', 'highlightbackground'):
                        values[key] = 'black'
                    elif key in ('foreground', 'activeforeground'):
                        values[key] = self._readable(values[key] or foreground)
        else:
            values = dict(original)
        if record['enabled'] and not record['ttk']:
            for key in values:
                if key in ('background', 'activebackground', 'selectcolor', 'highlightbackground'):
                    values[key] = 'black'
                elif key in ('foreground', 'activeforeground'):
                    values[key] = self._readable(values[key])
        changed = {key: value for key, value in values.items()
                   if str(widget.cget(key)) != str(value)}
        if changed:
            record['native'](**changed)
        record['signature'] = signature

    def _watch(self, widget):
        themed = isinstance(widget, ttk.Widget)
        keys = widget.keys()
        if themed:
            # Keep progress indicators and domain-drawn visuals in their own styles.
            if widget.winfo_class() not in ('TFrame', 'TLabel', 'TLabelframe', 'TButton',
                    'TCheckbutton', 'TRadiobutton', 'TEntry', 'TCombobox', 'Treeview'):
                return None
            values = {'style': str(widget.cget('style'))}
            # ttk.Label supports explicit colours which beat its style. Pioneer
            # and BioScan use these for content inside their scrollable panels.
            values.update({key: widget.cget(key) for key in ('background', 'foreground',
                'activebackground', 'activeforeground', 'selectcolor', 'highlightbackground') if key in keys})
        else:
            values = {key: widget.cget(key) for key in ('background', 'foreground',
                'activebackground', 'activeforeground', 'selectcolor', 'highlightbackground') if key in keys}
            if 'background' not in values:
                return None
        record = dict(values=values, native=widget.configure, native_config=widget.config,
                      enabled=False, ttk=themed, forced_style='')
        def configure(cnf=None, **kwargs):
            if cnf is not None and not isinstance(cnf, dict):
                return record['native'](cnf, **kwargs)
            options = dict(cnf or {})
            options.update(kwargs)
            if not options:
                return record['native']()
            options = {('background' if k == 'bg' else 'foreground' if k == 'fg' else k): v
                       for k, v in options.items()}
            for key in record['values']:
                if key not in options:
                    continue
                requested = options[key]
                # Plugins sometimes derive a child colour from an already-painted
                # parent. Keep its real theme colour for restoration in that case.
                derived = (record['enabled'] and (
                    key in ('background', 'activebackground', 'selectcolor', 'highlightbackground')
                    and self._same(requested, 'black')
                    or key in ('foreground', 'activeforeground') and self._same(requested, 'white')
                    or key == 'style' and str(requested) == record['forced_style']))
                if not derived:
                    record['values'][key] = requested
                if record['enabled']:
                    if key == 'style':
                        options[key] = record['forced_style']
                    elif key in ('foreground', 'activeforeground'):
                        options[key] = self._readable(record['values'][key])
                    else:
                        options[key] = 'black'
            style_requested = themed and 'style' in options
            # Theme handlers may repeatedly request their usual colours. Once
            # translated to the forced colour, an unchanged value needs no Tcl write.
            options = {key: value for key, value in options.items()
                       if key not in record['values'] or str(widget.cget(key)) != str(value)}
            result = record['native'](**options) if options else None
            if style_requested and record['enabled']:
                self._paint(widget, record)
            return result
        record['wrapper'] = configure
        widget.configure = widget.config = configure
        self.records[widget] = record
        return record

    def sync(self, panels):
        seen = set()
        for identity, _, panel in panels:
            folder = identity.split(':', 1)[-1]
            enabled = self.enabled(folder)
            pending = [panel]
            while pending:
                widget = pending.pop()
                try:
                    if isinstance(widget, tk.Toplevel):
                        continue
                    pending.extend(widget.winfo_children())
                    seen.add(widget)
                    record = self.records.get(widget)
                    if record is None and enabled:
                        record = self._watch(widget)
                    if record is not None:
                        changed = record['enabled'] != enabled
                        record['enabled'] = enabled
                        if changed or enabled:
                            self._paint(widget, record)
                except tk.TclError:
                    continue
        for widget in list(self.records):
            if widget not in seen:
                self._release(widget)

    def _release(self, widget):
        record = self.records.pop(widget)
        try:
            record['enabled'] = False
            self._paint(widget, record)
            if widget.configure is record['wrapper']:
                widget.configure = record['native']
            if widget.config is record['wrapper']:
                widget.config = record['native_config']
        except tk.TclError:
            pass

    def close(self):
        for widget in list(self.records):
            self._release(widget)
        self.drafts.clear()
