# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Ship cargo presentation from EDMC journal snapshots; no network or file polling."""
from __future__ import annotations

import re


def quantity(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        return number if number >= 0 and number == float(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


class CargoManifest:
    def __init__(self):
        self.counts = {}
        self.names = {}
        self.capacity = None
        self.known = False

    def update(self, entry, state):
        if entry.get('event') in ('LoadGame', 'Commander'):
            self.counts.clear()
            self.names.clear()
            self.capacity = None
            self.known = False

        capacity = quantity(state.get('CargoCapacity'))
        if entry.get('event') == 'Loadout':
            capacity = quantity(entry.get('CargoCapacity')) if 'CargoCapacity' in entry else capacity
        if capacity is not None:
            self.capacity = capacity

        # SRV snapshots must never replace the ship's manifest.
        is_srv = entry.get('event') == 'Cargo' and entry.get('Vessel') == 'SRV'
        snapshot = entry if entry.get('event') == 'Cargo' and not is_srv else state.get('CargoJSON')
        inventory = None
        if isinstance(snapshot, dict) and snapshot.get('Vessel', 'Ship') == 'Ship':
            inventory = snapshot.get('Inventory')
        if isinstance(inventory, list):
            for item in inventory:
                if not isinstance(item, dict):
                    continue
                key = str(item.get('Name') or '').casefold()
                if key and item.get('Name_Localised'):
                    self.names[key] = str(item['Name_Localised'])

        if entry.get('Type') and entry.get('Type_Localised'):
            self.names[str(entry['Type']).casefold()] = str(entry['Type_Localised'])

        # EDMC maintains totals across buys, sales, transfers, mining, etc.
        # Prefer them to a CargoJSON inventory which can be an older snapshot.
        if isinstance(state.get('Cargo'), dict) and not is_srv:
            self.counts = {str(key).casefold(): count for key, value in state['Cargo'].items()
                           if (count := quantity(value)) is not None and count > 0}
            self.known = True
        elif entry.get('event') == 'Cargo' and not is_srv and isinstance(inventory, list):
            self.counts = {}
            for item in inventory:
                if not isinstance(item, dict):
                    continue
                key, count = str(item.get('Name') or '').casefold(), quantity(item.get('Count'))
                if key and count:
                    self.counts[key] = self.counts.get(key, 0) + count
            self.known = True

    def rows(self):
        def name(key):
            if key in self.names:
                return self.names[key]
            if key == 'drones':
                return 'Limpets'
            return re.sub(r'[_\-]+', ' ', key.strip('$;')).title()
        return sorted(((name(key), count) for key, count in self.counts.items()),
                      key=lambda row: row[0].casefold())

    def summary(self):
        if not self.known:
            return 'Waiting for ship cargo data'
        total = sum(self.counts.values())
        return f'Cargo: {total:,}' + (f' / {self.capacity:,} t' if self.capacity is not None else ' t')
