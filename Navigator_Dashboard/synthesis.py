# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Material snapshots and recipe counts, independent of the GUI or recipe selection."""
from __future__ import annotations

try:
    from .cargo import quantity
except ImportError:
    from cargo import quantity

CATEGORIES = ('Raw', 'Manufactured', 'Encoded')

# Factual recipe data is separate from inventory and presentation code.
import json
import os
with open(os.path.join(os.path.dirname(__file__), 'recipes.json'), encoding='utf-8') as stream:
    _data = json.load(stream)
RECIPES = {row['id']: dict(name=row['name'], grades=tuple(
    (grade['level'], {(item['category'], item['name']): item['count'] for item in grade['materials']})
    for grade in row['grades'])) for row in _data['recipes']}
GROUPS = {name: tuple(ids) for name, ids in _data['groups'].items()}
FSD_RECIPES = tuple(recipe for _level, recipe in RECIPES['fsd']['grades'])
FSD_GRADES = ('I', 'II', 'III')



class SynthesisInventory:
    def __init__(self):
        self.materials = {}
        self.known = set()

    def update(self, entry, state):
        if entry.get('event') in ('LoadGame', 'Commander'):
            self.materials.clear()
            self.known.clear()
        for category in CATEGORIES:
            values = state.get(category)
            if isinstance(values, dict):
                self.materials[category] = {str(key).casefold(): count
                    for key, value in values.items() if (count := quantity(value)) is not None}
                self.known.add(category)
            elif entry.get('event') == 'Materials' and isinstance(entry.get(category), list):
                self.materials[category] = {str(item['Name']).casefold(): count
                    for item in entry[category] if isinstance(item, dict) and item.get('Name')
                    and (count := quantity(item.get('Count'))) is not None}
                self.known.add(category)

    def available(self, recipe):
        """Independent uses of a recipe: {(category, material): units_per_use}.

        None means a needed material category has not been received yet.
        These counts share inventory, so different recipes cannot be added together.
        """
        if not recipe:
            raise ValueError('A recipe needs at least one material')
        counts = []
        for (category, name), needed in recipe.items():
            amount = quantity(needed)
            if amount is None or amount == 0 or category not in CATEGORIES:
                raise ValueError('Invalid recipe requirement')
            if category not in self.known:
                return None
            counts.append(self.materials[category].get(name.casefold(), 0) // amount)
        return min(counts)

    def fsd_injections(self):
        return tuple(self.available(recipe) for recipe in FSD_RECIPES)

    def fsd_line(self):
        counts = self.fsd_injections()
        amounts = ('?' if count is None else f'{count:,}' for count in counts)
        return 'FSD Injection: ' + ' / '.join(amounts)

    def group_rows(self, group='Exploration'):
        return tuple((key, RECIPES[key]['name'], tuple(
            (level, self.available(recipe)) for level, recipe in RECIPES[key]['grades']))
            for key in GROUPS.get(group, GROUPS['Exploration']))
