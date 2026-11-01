# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Optional per-plugin header names. Never import or start another plugin."""
import json
import tkinter as tk
from tkinter import ttk, simpledialog
from types import SimpleNamespace

CONFIG = 'NavInterface_CustomHeaders'


def walk(widget):
    for child in widget.winfo_children():
        if not isinstance(child, tk.Toplevel):
            yield child
            yield from walk(child)


class CustomHeaders:
    def __init__(self, namespace):
        self.ns = namespace

    def saved(self):
        try:
            data = json.loads(self.ns['_get_str'](CONFIG, '{}'))
        except (ValueError, TypeError):
            return {}
        return {k: v.strip()[:80] for k, v in data.items() if isinstance(k, str)
                and isinstance(v, str) and v.strip()} if isinstance(data, dict) else {}

    def label(self, panel, plugin):
        # First use explicit, already loaded header widgets where available.
        module = getattr(plugin, 'module', None)
        explicit = [getattr(module, '_title_label', None)]
        ui = getattr(module, '_ui', {})
        if isinstance(ui, dict):
            explicit.append(ui.get('header'))
        for state in (self.ns['_bioscan_state'](), self.ns['_panel_state']('pioneer.globals', 'pioneer_globals')):
            explicit.append(getattr(state, 'label', None))
        descendants = list(walk(panel))
        for widget in explicit:
            if widget in descendants and isinstance(widget, (tk.Label, ttk.Label)):
                return widget
        # A stock collapse button identifies the actual header container.
        buttons = list(self.ns['_profile_buttons'](panel))
        containers = [button.master for button in buttons]
        def text_label(w):
            return isinstance(w, (tk.Label, ttk.Label)) and (str(w.cget('text')).strip() or str(w.cget('textvariable')))
        for container in containers:
            for widget in walk(container):
                if text_label(widget):
                    return widget
        # Panels without collapse (e.g. Docking) can still have a matching title.
        import re
        normalized = lambda value: re.sub(r'[^a-z0-9]', '', value.casefold())
        names = [normalized(str(getattr(plugin, 'name', ''))),
                 normalized(str(getattr(plugin, 'folder', '')).split('/')[-1].split('\\')[-1])]
        for widget in descendants:
            if text_label(widget):
                title = normalized(str(widget.cget('text')).split('\n')[0].replace('(Hidden)', ''))
                if title and any(name and (name.startswith(title) or title.startswith(name)) for name in names):
                    return widget
        return None

    def installed(self):
        module = self.ns['sys'].modules.get('plug')
        panels = {identity: widget for identity, _, widget in self.ns['_plugin_panels']()}
        result = []
        for plugin in getattr(module, 'PLUGINS', ()):
            name = str(getattr(plugin, 'name', 'Plugin'))
            folder = getattr(plugin, 'folder', None)
            identity = f'folder:{folder}' if folder else f'name:{name}'
            panel = panels.get(identity)
            label = self.label(panel, plugin) if panel is not None else None
            # textvariable labels need a trace adapter; don't detach their data binding.
            available = label is not None and not str(label.cget('textvariable'))
            result.append((identity, name, panel, label if available else None))
        return result

    def targets(self):
        names = self.saved()
        if not names:return {}
        return {label: (SimpleNamespace(navigator_custom_header=True, panel=panel), '', names[identity])
                for identity, _, panel, label in self.installed() if label is not None and identity in names}

    def prefs(self, parent, row=0, column=1):
        frame = ttk.LabelFrame(parent, text='Custom Plugin Headers', padding=6)
        frame.grid(row=row, column=column, rowspan=4, sticky='nsew', padx=(16, 0))
        frame.columnconfigure(0, weight=1)
        draft = self.saved()
        self.ns['_prefs']['custom_headers'] = draft
        records = self.installed()
        tree = ttk.Treeview(frame, columns=('custom',), show='tree headings', height=4, selectmode='browse')
        tree.heading('#0', text='Installed Plugin');tree.heading('custom', text='Custom Header')
        tree.column('#0', width=175, minwidth=100);tree.column('custom', width=155, minwidth=90)
        tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns');tree.configure(yscrollcommand=scrollbar.set)
        for identity, name, _, label in records:
            tree.insert('', 'end', iid=identity, text=name,
                values=(draft.get(identity, '') if label is not None else 'No Visible Header',))
        controls = ttk.Frame(frame);controls.grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
        def selected():
            ids = tree.selection()
            return next((r for r in records if ids and r[0] == ids[0]), None)
        def edit():
            record = selected()
            if not record or record[3] is None:return
            identity, name, _, _ = record
            value = simpledialog.askstring('Custom Header', f'Header for {name}:\nLeave blank for default.',
                initialvalue=draft.get(identity, ''), parent=frame)
            if value is None:return
            value = ' '.join(value.split())[:80]
            if value:draft[identity] = value
            else:draft.pop(identity, None)
            tree.set(identity, 'custom', value)
        def reset():
            record = selected()
            if record:
                draft.pop(record[0], None)
                tree.set(record[0], 'custom', '' if record[3] is not None else 'No Visible Header')
        edit_button = ttk.Button(controls, text='Custom Header', command=edit);edit_button.pack(side='left')
        ttk.Button(controls, text='Reset To Default', command=reset).pack(side='left', padx=(6, 0))
        def selection(_event=None):
            record = selected()
            edit_button.configure(state='normal' if record and record[3] is not None else 'disabled')
        tree.bind('<<TreeviewSelect>>', selection);tree.bind('<Return>', lambda e:edit())
        if records:tree.selection_set(records[0][0])
        selection()
        ttk.Label(frame, text='Custom name wins over purpose labels. Apply/OK saves; Reset restores normal behavior.',
                  wraplength=340, justify='left').grid(row=2, column=0, columnspan=2, sticky='w')
        self.ns['_prefs']['header_tree'] = tree
        self.ns['_prefs']['header_edit'] = edit
        self.ns['_prefs']['header_reset'] = reset

    def save(self):
        draft = self.ns['_prefs'].get('custom_headers')
        if isinstance(draft, dict):
            self.ns['config'].set(CONFIG, json.dumps(draft, ensure_ascii=False))
