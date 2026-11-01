# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Scoped Settings styling and font-sized tables. Event driven; no theme polling."""
import sys
import tkinter as tk
from tkinter import ttk, font as tkfont


class SettingsCompat:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.style = ttk.Style(root)
        self.windows, self.pending, self.originals, self.tables = set(), {}, {}, {}
        self.layouts, self.elements = set(), set()
        self.signature = None
        self.window_dark = {}
        self.caption_signatures = {}
        self.closing = False
        self.bindings = []
        self.font = tkfont.Font(root=root, font='TkDefaultFont')
        if self.font.actual('family').casefold() == 'euro caps':
            self.font.configure(family='Segoe UI' if sys.platform == 'win32' else 'TkDefaultFont')
        for event in ('<Map>', '<Destroy>', '<<ThemeChanged>>', '<<NavigatorThemeChanged>>'):
            self.bindings.append((event, root.bind_all(event, self.event, add='+')))

    def attach(self, widget):
        window = widget.winfo_toplevel()
        if window is self.root:return
        self.windows.add(window)
        self.schedule(window)

    def event(self, event):
        if self.closing:return
        if event.type == tk.EventType.Destroy:
            record = self.originals.pop(event.widget, {})
            if '_postcommand' in record:
                try:self.root.deletecommand(record['_postcommand'][2])
                except tk.TclError:pass
            self.tables.pop(event.widget, None)
            if event.widget in self.windows:
                self.windows.discard(event.widget)
                self.window_dark.pop(event.widget, None)
                self.caption_signatures.pop(event.widget, None)
                job = self.pending.pop(event.widget, None)
                if job:
                    try:self.root.after_cancel(job)
                    except tk.TclError:pass
            return
        if getattr(event, 'widget', None) is self.root and str(event.type) == '35':
            for window in list(self.windows):self.schedule(window)
            return
        try:
            window = event.widget.winfo_toplevel()
            if window not in self.windows and window is not self.root:
                parent = getattr(window,'master',None)
                if parent is not None and parent.winfo_toplevel() in self.windows:
                    self.windows.add(window)
            if window in self.windows:self.schedule(window)
        except (tk.TclError, AttributeError):pass

    def schedule(self, window):
        if not self.closing and window not in self.pending:
            self.pending[window] = self.root.after_idle(lambda:self.apply(window))

    def palette(self):
        dark = bool(self.config.get_int('theme', default=0))
        normal = self.config.get_str('dark_text', default='#ff8000') or '#ff8000'
        highlight = self.config.get_str('dark_highlight', default='white') or 'white'
        background = '#101010'
        try:
            from theme import theme
            current = getattr(theme, 'current', {}) or {}
            background = current.get('background') or background
        except (ImportError, AttributeError):pass
        # Transparent main windows still get a fully opaque Settings dialog.
        for color in (normal, highlight, background):self.root.winfo_rgb(color)
        return dark, background, normal, highlight

    def mix(self, a, b, fraction):
        left, right = self.root.winfo_rgb(a), self.root.winfo_rgb(b)
        return '#' + ''.join(f'{round((x*(1-fraction)+y*fraction)/257):02x}' for x,y in zip(left,right))

    def layout(self, target, base):
        theme = self.style.theme_use()
        key = theme, target
        if key in self.layouts:return
        raw = self.root.tk.call('ttk::style', 'theme', 'settings', 'clam',
                                self.root.tk.call('list', 'ttk::style', 'layout', base))
        def parse(values):
            values = self.root.tk.splitlist(values) if isinstance(values, str) else values
            result, i = [], 0
            while i < len(values):
                element = str(values[i]);i += 1
                # Treeview's C renderer locates these semantic elements by name.
                # Renaming them produces a painted field with no rows/headings.
                semantic = element in ('Treeview.treearea','Treeheading.text','Treeheading.image')
                renamed = element if semantic else 'NavPrefs_' + theme + '_' + element
                if not semantic and (theme, element) not in self.elements:
                    if renamed not in self.style.element_names():
                        self.style.element_create(renamed, 'from', 'clam', element)
                    self.elements.add((theme, element))
                options = {}
                while i < len(values) and str(values[i]).startswith('-'):
                    name, value = str(values[i])[1:], values[i+1];i += 2
                    options[name] = parse(value) if name == 'children' else value
                result.append((renamed, options))
            return result
        self.style.layout(target, parse(raw))
        self.layouts.add(key)

    def configure_styles(self, palette):
        signature = (self.style.theme_use(), palette, tuple(sorted(self.font.actual().items())))
        if signature == self.signature:return
        _, bg, fg, hi = palette
        field, selection, muted = self.mix(bg, fg, .07), self.mix(bg, hi, .22), self.mix(bg, fg, .5)
        bases = ('TFrame','TLabel','TLabelframe','TLabelframe.Label','TButton','TMenubutton','TCheckbutton','TRadiobutton',
                 'TEntry','TCombobox','TSpinbox','TNotebook','TNotebook.Tab','Treeview','Treeview.Heading',
                 'Horizontal.TScrollbar','Vertical.TScrollbar','Horizontal.TScale','Vertical.TScale','TSeparator',
                 'Horizontal.TSeparator','Vertical.TSeparator')
        for base in bases:
            name = 'NavPrefs.' + base
            try:self.layout(name, base)
            except tk.TclError:pass  # A new/custom widget can retain its native layout.
            self.style.configure(name, background=bg, foreground=fg, fieldbackground=field,
                font=self.font, bordercolor=muted, lightcolor=bg, darkcolor=bg, troughcolor=field,
                arrowcolor=fg, insertcolor=fg, selectbackground=selection, selectforeground=hi)
            self.style.map(name, foreground=[('disabled',muted),('selected',hi),('active',hi)],
                background=[('selected',selection),('active',field)],
                fieldbackground=[('readonly',field),('disabled',bg)])
        self.style.configure('NavPrefs.TButton', foreground=hi, padding=(6,3))
        # Section dividers: a dim theme line instead of Windows' bright native one.
        line = self.mix(bg, fg, .25)
        for name in ('NavPrefs.TSeparator','NavPrefs.Horizontal.TSeparator','NavPrefs.Vertical.TSeparator'):
            self.style.configure(name, background=line, lightcolor=line, darkcolor=line, bordercolor=line)
        self.style.configure('NavPrefs.TMenubutton', padding=(5,2))
        for base in ('TCheckbutton','TRadiobutton'):
            name = 'NavPrefs.'+base
            self.style.configure(name, indicatorsize=max(12,self.font.metrics('linespace')-3),
                indicatormargin=(0,2,5,2), indicatorbackground=field,
                indicatorforeground=hi, upperbordercolor=muted, lowerbordercolor=muted)
            # A checked option needs an indicator, not a filled label background.
            self.style.map(name, background=[('active',field)],
                foreground=[('disabled',muted)],
                indicatorforeground=[('disabled',muted),('selected',hi)],
                indicatorbackground=[('disabled',bg),('active',selection)])
        self.style.configure('NavPrefs.Treeview', rowheight=self.font.metrics('linespace')+6)
        self.style.configure('NavPrefs.Treeview.Heading', padding=(4,4))
        self.style.configure('NavPrefs.TNotebook.Tab', padding=(7,4))
        self.signature = signature

    def remember(self, widget):
        if widget not in self.originals:
            self.originals[widget] = {}
        return self.originals[widget]

    def set_options(self, widget, options):
        original = self.remember(widget)
        changed = {}
        for key, value in options.items():
            if key in widget.keys() and str(widget.cget(key)) != str(value):
                original.setdefault(key, widget.cget(key))
                changed[key] = value
        if changed:widget.configure(**changed)

    def horizontal_table(self, widget):
        if widget in self.tables or str(widget.cget('xscrollcommand')):return
        manager = widget.winfo_manager()
        if manager not in ('grid', 'pack'):return
        info = getattr(widget, manager+'_info')()
        wrapper = ttk.Frame(widget.master, style='NavPrefs.TFrame')
        getattr(widget, manager+'_forget')()
        getattr(wrapper, manager)(**info)
        wrapper.columnconfigure(0, weight=1);wrapper.rowconfigure(0, weight=1)
        widget.grid(in_=wrapper, row=0, column=0, sticky='nsew')
        widget.lift(wrapper)  # Same actual Tk parent: don't let the newer wrapper cover the rows.
        bar = ttk.Scrollbar(wrapper, orient='horizontal', command=widget.xview,
                            style='NavPrefs.Horizontal.TScrollbar')
        bar.grid(row=1, column=0, sticky='ew')
        widget.configure(xscrollcommand=bar.set)
        self.tables[widget] = (wrapper, manager, info)

    def table(self, widget, dark):
        original = self.remember(widget)
        original.setdefault('_columns', {})
        original.setdefault('_applied_widths', {})
        if '_insert' not in original:
            native = widget.insert
            def insert(*args,**kwargs):
                result = native(*args,**kwargs)
                try:self.schedule(widget.winfo_toplevel())
                except tk.TclError:pass
                return result
            original['_insert'] = (native,insert)
            widget.insert = insert
        columns = list(widget.cget('columns'))
        if 'tree' in str(widget.cget('show')):columns.insert(0, '#0')
        # Keep custom row heights when larger (e.g. a plugin's image rows).
        old_style = str(original.get('style') or 'Treeview')
        try:old_height = int(self.style.lookup(old_style, 'rowheight') or 0)
        except (TypeError, ValueError):old_height = 0
        target = 'NavPrefs.Treeview' if dark else 'NavPrefs.Light.Treeview'
        if not dark:
            height=max(old_height,self.font.metrics('linespace')+6)
            if (str(self.style.lookup(target,'font'))!=str(self.font)
                    or str(self.style.lookup(target,'rowheight'))!=str(height)):
                self.style.configure(target, font=self.font,rowheight=height)
        elif old_height > self.font.metrics('linespace')+6:
            if str(self.style.lookup(target,'rowheight'))!=str(old_height):
                self.style.configure(target, rowheight=old_height)
        self.set_options(widget, {'style':target})
        rows = widget.get_children('')[:150]
        # Measure with the font the rows are actually drawn in, plus the tree indent.
        try:
            row_font = tkfont.Font(font=self.style.lookup(target, 'font') or self.font)
        except tk.TclError:
            row_font = self.font
        try:
            indent = int(float(self.style.lookup(target, 'indent') or 20))
        except (TypeError, ValueError):
            indent = 20
        for position, column in enumerate(columns):
            original['_columns'].setdefault(column, widget.column(column))
            heading = str(widget.heading(column, 'text'))
            samples = [str(widget.item(row, 'text') if column=='#0' else widget.set(row,column)) for row in rows]
            extra = 20 + (indent if column == '#0' else 0)
            measured = max([self.font.measure(heading)+24]+[row_font.measure(value)+extra for value in samples])
            minimum = max(55, self.font.measure(heading)+20)
            width = max(minimum, min(420, measured))
            current = int(widget.column(column,'width'))
            last = original['_applied_widths'].get(column)
            if last is None or current==last:
                # The last column stretches to fill the box; the others keep their width.
                if last is None:widget.column(column,stretch=position == len(columns)-1)
                if current < width:widget.column(column,width=width,minwidth=minimum)
                original['_applied_widths'][column]=int(widget.column(column,'width'))
        self.horizontal_table(widget)

    def combobox(self, widget, palette):
        record = self.remember(widget)
        if '_postcommand' in record:return
        previous = str(widget.cget('postcommand'))
        def popup():
            try:
                _, bg, fg, hi = self.palette()
                popdown = self.root.tk.call('ttk::combobox::PopdownWindow', str(widget))
                path = str(popdown)+'.f.l'
                if '_popdown' not in record:
                    record['_popdown'] = (path,{key:self.root.tk.call(path,'cget','-'+key)
                        for key in ('background','foreground','selectbackground','selectforeground','font')})
                self.root.tk.call(path, 'configure', '-background',bg,
                    '-foreground',fg,'-selectbackground',self.mix(bg,hi,.22),'-selectforeground',hi,'-font',str(self.font))
            except tk.TclError:pass
        command = self.root.register(popup)
        combined = (previous+'; ' if previous else '')+command
        record['_postcommand'] = (previous, combined, command)
        widget.configure(postcommand=combined)

    def caption(self, window, dark, bg, fg):
        if sys.platform != 'win32' or not window.winfo_ismapped():return
        signature = dark,bg,fg
        if self.caption_signatures.get(window)==signature:return
        self.caption_signatures[window]=signature
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            def set_attribute(number, value):
                data = ctypes.c_uint(value)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, number, ctypes.byref(data), ctypes.sizeof(data))
            set_attribute(20, int(dark))
            def color(value):
                r,g,b = (v//257 for v in window.winfo_rgb(value))
                return r | (g<<8) | (b<<16)
            set_attribute(35, color(bg) if dark else 0xffffffff)
            set_attribute(36, color(fg) if dark else 0xffffffff)
        except (AttributeError, OSError, tk.TclError):pass

    def restore_widget(self, widget, record):
        if not widget.winfo_exists():return
        if '_insert' in record:
            native,wrapper = record['_insert']
            if widget.insert is wrapper:widget.insert = native
        columns = record.get('_columns', {})
        for col, options in columns.items():
            try:widget.column(col, **{k:v for k,v in options.items() if k!='id'})
            except tk.TclError:pass
        if '_popdown' in record:
            path,options = record['_popdown']
            if self.root.tk.call('winfo','exists',path):
                self.root.tk.call(path,'configure',*[v for k,value in options.items() for v in ('-'+k,value)])
        post = record.get('_postcommand')
        if post:
            old, ours, command = post
            if str(widget.cget('postcommand')) == ours:widget.configure(postcommand=old)
            try:self.root.deletecommand(command)
            except tk.TclError:pass
        options = {k:v for k,v in record.items() if not k.startswith('_')}
        if options:widget.configure(**options)

    def color_preview(self, widget, window):
        # EDMC exposes its actual chooser buttons on PreferencesDialog. This
        # works with translated preview text and leaves every option/callback alone.
        if any(widget is getattr(window,name,None) for name in ('theme_button_0','theme_button_1')):
            return True
        if getattr(widget,'navigator_color_preview',False):
            return True  # a plugin's own colour swatch: keep the colour it shows
        # Compatibility with older EDMC dialogs and label-based previews.
        return (isinstance(widget,(tk.Button,tk.Label,ttk.Button,ttk.Label))
                and str(widget.cget('text')).strip() in ('Station','Hutton Orbital')
                and (isinstance(widget,(tk.Button,ttk.Button))
                     or str(widget.cget('background')) not in ('','SystemWindow')))

    def apply(self, window):
        self.pending.pop(window, None)
        if self.closing or not window.winfo_exists():return
        palette = self.palette();dark,bg,fg,hi = palette
        if dark:self.configure_styles(palette)
        # Remove our prior colors first when returning to the Default theme.
        if not dark and self.window_dark.get(window,False):
            for widget, record in list(self.originals.items()):
                try:
                    if widget.winfo_toplevel() is window:
                        self.restore_widget(widget, record)
                        self.originals.pop(widget, None)
                except tk.TclError:self.originals.pop(widget, None)
            for tree,(wrapper,_,_) in list(self.tables.items()):
                if wrapper.winfo_exists() and wrapper.winfo_toplevel() is window:
                    wrapper.configure(style='TFrame')
                    for bar in wrapper.winfo_children():
                        if isinstance(bar,ttk.Scrollbar):bar.configure(style='Horizontal.TScrollbar')
        self.window_dark[window] = dark
        pending = [window]
        while pending:
            widget = pending.pop()
            try:
                pending.extend(child for child in widget.winfo_children() if not isinstance(child, tk.Toplevel))
                if self.color_preview(widget,window):continue
                if isinstance(widget, ttk.Widget):
                    base = widget.winfo_class()
                    if isinstance(widget, (ttk.Scrollbar, ttk.Scale, ttk.Separator)):
                        base = str(widget.cget('orient')).title()+'.'+base
                    if dark:
                        target = 'NavPrefs.'+base
                        self.set_options(widget, {'style':target})
                        # myNotebook.Label sets Windows light colors directly on
                        # the widget; these override any ttk style we assign.
                        options = {}
                        keys = widget.keys()
                        if 'background' in keys:options['background']=bg
                        if 'foreground' in keys:
                            clickable = ('cursor' in keys and str(widget.cget('cursor')) in ('hand1','hand2'))
                            options['foreground']=hi if clickable else fg
                        if 'font' in keys:options['font']=self.font
                        self.set_options(widget,options)
                    if isinstance(widget, ttk.Treeview):self.table(widget,dark)
                    if dark and isinstance(widget, ttk.Combobox):self.combobox(widget,palette)
                elif dark:
                    options = {'background':bg}
                    if 'font' in widget.keys():options['font'] = self.font
                    if 'foreground' in widget.keys():
                        old = str(widget.cget('foreground'))
                        clickable = str(widget.cget('cursor')) in ('hand2','hand1') if 'cursor' in widget.keys() else False
                        options['foreground'] = hi if old == hi or clickable or isinstance(widget, tk.Button) else fg
                    for key,value in (('insertbackground',fg),('selectbackground',self.mix(bg,hi,.22)),
                                      ('selectforeground',hi),('activebackground',self.mix(bg,fg,.1)),
                                      ('activeforeground',hi),('highlightbackground',bg),('troughcolor',self.mix(bg,fg,.07))):
                        if key in widget.keys():options[key]=value
                    self.set_options(widget, options)
            except tk.TclError:continue
        self.caption(window,dark,bg,fg)

    def close(self):
        self.closing = True
        for event, binding in self.bindings:
            self.root._unbind(('bind','all',event), binding)
        for job in self.pending.values():
            try:self.root.after_cancel(job)
            except tk.TclError:pass
        self.pending.clear()
        for widget,(wrapper,manager,info) in list(self.tables.items()):
            try:
                if widget.winfo_exists():
                    widget.grid_forget();wrapper.destroy()
                    getattr(widget,manager)(**info);widget.configure(xscrollcommand='')
            except tk.TclError:pass
        for widget,record in list(self.originals.items()):
            try:self.restore_widget(widget,record)
            except tk.TclError:pass
        for window in self.windows:
            try:self.caption(window,False,'white','black')
            except tk.TclError:pass
        self.originals.clear();self.tables.clear();self.windows.clear();self.window_dark.clear();self.caption_signatures.clear()
