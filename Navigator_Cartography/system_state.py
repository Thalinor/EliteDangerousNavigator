# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Current-system context for future Systems Navigator fields; no UI or I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemContext:
    commander: str = ""
    is_beta: bool = False
    name: str | None = None
    address: int | None = None
    coordinates: tuple[float, float, float] | None = None
    station: str | None = None
    # Future system-specific information belongs here and clears on arrival.
    details: dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.name = self.address = self.coordinates = self.station = None
        self.details.clear()

    def update(self, commander: str, is_beta: bool, system: str | None,
               station: str | None, entry: dict[str, Any]) -> None:
        event = entry.get("event")
        if commander != self.commander or bool(is_beta) != self.is_beta:
            self.clear()
        self.commander, self.is_beta = commander, bool(is_beta)
        if event == "LoadGame":
            self.clear()
            return  # wait for Location rather than reusing previous-session context
        arrival = event in ("Location", "FSDJump", "CarrierJump")
        name = (entry.get("StarSystem") if arrival else None) or system
        address = entry.get("SystemAddress") if arrival else None
        if not isinstance(address, int) or isinstance(address, bool):
            address = None
        changed = ((name is not None and self.name is not None and name.casefold() != self.name.casefold())
                   or (address is not None and self.address is not None and address != self.address))
        if changed:
            self.clear()
        if name:
            self.name = name
        if address is not None:
            self.address = address
        if arrival:
            position = entry.get("StarPos")
            if (isinstance(position, (list, tuple)) and len(position) == 3
                    and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in position)):
                self.coordinates = tuple(float(n) for n in position)
        self.station = station
