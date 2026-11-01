# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""No-fire-zone session state and reversible EDMC panel visibility."""
import re
import tkinter as tk

from .core import event_age


class DockingSession:
    def __init__(self):
        self.active = self.inside = self.docked = self.blocked = False

    def journal(self, entry):
        before = self.active
        event = entry.get('event')
        message = str(entry.get('Message', '')).casefold()
        if event == 'ReceiveText' and entry.get('Channel', 'npc') == 'npc' and event_age(entry) <= 60:
            if message == '$station_nofirezone_entered;':
                if not self.inside:
                    self.inside = True
                    self.blocked = self.docked
                    self.active = not self.docked
            elif message == '$station_nofirezone_exited;':
                self.active = self.inside = self.blocked = False
        elif event == 'Docked':
            self.docked = self.blocked = True
            self.active = False
        elif event == 'Undocked':
            self.docked = self.active = False
            self.blocked = self.inside  # Do not reopen during departure.
        elif event in {'DockingRequested', 'DockingGranted'} and event_age(entry) <= 120 and not self.docked:
            self.inside = self.active = True  # Claude's startup-inside-zone fallback.
        elif event == 'Location':
            self.active = self.inside = False
            self.docked = self.blocked = bool(entry.get('Docked'))
        elif event in {'LoadGame', 'Commander', 'StartJump', 'FSDJump', 'CarrierJump',
                       'SupercruiseEntry', 'Shutdown', 'Died', 'Resurrect'} or (
                event == 'Music' and entry.get('MusicTrack') == 'MainMenu'):
            self.active = self.inside = self.docked = self.blocked = False
        # Denied/cancelled/timeout remain visible inside the zone for a retry.
        return before != self.active

    def dashboard(self, entry):
        before = self.active
        flags = entry.get('Flags')
        if isinstance(flags, int) and not isinstance(flags, bool):
            self.docked = bool(flags & 1)
            if self.docked:
                self.blocked, self.active = True, False
            elif flags & 16:  # Supercruise: also recover if the journal exit was missed.
                self.active = self.inside = self.blocked = False
        return before != self.active


class PanelFocus:
    """Hide whole wrappers; never invoke or change another plugin's arrow state.

    EDMC names plugin wrappers plugin_N and their separators plugin_hr_N.
    Grid removal retains live widgets, text, scroll position and callbacks.
    One snapshot per approach prevents repeated messages overwriting it.
    """
    def __init__(self, view):
        self.view = view
        parent = view.master
        self.host = parent if re.fullmatch(r'plugin_\d+', parent.winfo_name()) else view
        self.main = self.host.master if self.host is parent else None
        self.others, self.own = {}, {}
        self.collapsed, self.handled = [], set()

    @staticmethod
    def _hide(widget, snapshots, remember_unmapped=True):
        manager = widget.winfo_manager()
        if widget not in snapshots and (manager or remember_unmapped):
            info = getattr(widget, f'{manager}_info')() if manager else {}
            info.pop('in', None)
            snapshots[widget] = manager, info
        if manager:
            getattr(widget, 'grid_remove' if manager == 'grid' else f'{manager}_forget')()

    @staticmethod
    def _restore(snapshots):
        for widget, (manager, info) in list(snapshots.items()):
            try:
                if manager:
                    getattr(widget, manager)(**info)
                else:
                    PanelFocus._hide(widget, {})
            except tk.TclError:
                pass  # A plugin can be removed while an approach is active.
        snapshots.clear()

    def _own_widgets(self):
        widgets = [self.host]
        if self.main is not None:
            index = self.host.winfo_name().split('_')[-1]
            separator = self.main.children.get(f'plugin_hr_{index}')
            if separator is not None:
                widgets.append(separator)
        return widgets

    def _collapse_panel(self, widget):
        buttons, pending = [], list(widget.winfo_children())
        while pending:
            child = pending.pop(0)
            if isinstance(child, tk.Toplevel):
                continue
            if child.winfo_class() in {'Button', 'TButton'} and str(child.cget('text')).strip() in {'\U0001f53c','\U0001f53d'}:
                buttons.append(child)
            pending.extend(child.winfo_children())
        if not buttons:
            self._hide(widget, self.others)
            if self.main is not None:
                index = widget.winfo_name().split('_')[-1]
                separator = self.main.children.get(f'plugin_hr_{index}')
                if separator is not None:
                    self._hide(separator, self.others)
            return
        for button in buttons:
            if button.winfo_ismapped() and str(button.cget('text')).strip() == '\U0001f53c':
                self.collapsed.append(button)
                try:
                    button.invoke()
                except tk.TclError:
                    pass

    def _restore_panels(self):
        buttons, self.collapsed = self.collapsed, []
        self.handled.clear()
        for button in buttons:
            try:
                if button.winfo_exists() and str(button.cget('text')).strip() == '\U0001f53d':
                    button.invoke()
            except tk.TclError:
                pass
        self._restore(self.others)

    def sync(self, active, enabled=True):
        if active and enabled:
            self._restore(self.own)
            if self.main is not None:
                for name, widget in list(self.main.children.items()):
                    if widget is self.host or not re.fullmatch(r'plugin_\d+', name) or widget in self.handled:
                        continue
                    self.handled.add(widget)  # Set before invoke(): Pioneer calls update().
                    self._collapse_panel(widget)
        else:
            self._restore_panels()
            if enabled:
                for widget in self._own_widgets():
                    self._hide(widget, self.own, remember_unmapped=False)
            else:
                self._restore(self.own)

    def restore(self):
        self._restore_panels()
        self._restore(self.own)
