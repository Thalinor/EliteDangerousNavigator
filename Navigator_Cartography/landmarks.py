# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Known engineers, material traders and technology brokers. No GUI, network calls or timers here.

Engineers come from the bundled, verified engineers.json. Traders and brokers are
learned from journal/EDSM station services as the commander travels, and can be
seeded once from the optional station-data download.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_VERSION = 1
# Material trader type follows station economy exactly (checked against every Spansh trader).
# Technology broker type does not, so it stays unknown until a download says otherwise.
TRADER_BY_ECONOMY = {"extraction": "Raw", "refinery": "Raw", "industrial": "Manufactured", "hightech": "Encoded"}
GLYPHS = {"E": "⚙", "M": "⇄", "T": "◈"}   # gear, exchange arrows, diamond


def _norm(text) -> str:
    return "".join(ch for ch in str(text or "").casefold() if ch.isalnum())


def _value(row, key):
    item = row.get(key) if isinstance(row, dict) else None
    return item.get("v") if isinstance(item, dict) else None


def services(row) -> set[str]:
    """Normalised service names from either journal tokens or EDSM labels."""
    found = set()
    for item in _value(row, "services") or []:
        name = _norm(item.get("name") if isinstance(item, dict) else item)
        if name in {"materialtrader"}:
            found.add("M")
        elif name in {"techbroker", "technologybroker"}:
            found.add("T")
    return found


def economy_trader(row) -> str | None:
    economy = _norm(_value(row, "economy")).removeprefix("economy")
    return TRADER_BY_ECONOMY.get(economy)


class Landmarks:
    def __init__(self, plugin_dir: str | Path | None = None, data: dict | None = None):
        self.engineers_by_id: dict[str, str] = {}
        self.engineers_by_name: dict[tuple[str, str], str] = {}
        if plugin_dir is not None:
            try:
                with (Path(plugin_dir) / "engineers.json").open(encoding="utf-8") as f:
                    for item in json.load(f).get("engineers", []):
                        self.engineers_by_id[str(item["market_id"])] = item["engineer"]
                        self.engineers_by_name[(_norm(item["system"]), _norm(item["station"]))] = item["engineer"]
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.load(data)

    def load(self, data) -> None:
        data = data if isinstance(data, dict) and data.get("version") == DATA_VERSION else {}
        self.data = {"version": DATA_VERSION, "downloaded": data.get("downloaded"),
                     "stations": data.get("stations") if isinstance(data.get("stations"), dict) else {}}
        self._names = {(_norm(e.get("s")), _norm(e.get("n"))): key
                       for key, e in self.data["stations"].items() if isinstance(e, dict)}

    def snapshot(self) -> dict:
        """A copy the background worker can write while the UI keeps learning."""
        return {"version": DATA_VERSION, "downloaded": self.data["downloaded"],
                "stations": {k: dict(v) for k, v in self.data["stations"].items()}}

    @property
    def downloaded(self):
        return self.data["downloaded"]

    def __len__(self) -> int:
        return len(self.data["stations"])

    def engineer(self, system, row) -> str | None:
        mid = _value(row, "marketId")
        if mid is not None and str(mid) in self.engineers_by_id:
            return self.engineers_by_id[str(mid)]
        return self.engineers_by_name.get((_norm(system), _norm(_value(row, "name"))))

    def entry(self, system, row) -> dict | None:
        mid = _value(row, "marketId")
        if mid is not None and str(mid) in self.data["stations"]:
            return self.data["stations"][str(mid)]
        key = self._names.get((_norm(system), _norm(_value(row, "name"))))
        return self.data["stations"].get(key) if key else None

    def learn(self, system, row, coords=None) -> bool:
        """Remember a trader/broker station seen in play. True when something new was stored."""
        found = services(row)
        name = _value(row, "name")
        if not found or not name or not system:
            return False
        mid = _value(row, "marketId")
        existing = self.entry(system, row)
        if existing is None:
            key = str(mid) if mid is not None else "name:" + _norm(system) + "/" + _norm(name)
            existing = self.data["stations"].setdefault(key, {})
            self._names[(_norm(system), _norm(name))] = key
        before = dict(existing)
        pads = _value(row, "landingPads")
        pad = next((label for k, label in (("Large", "L"), ("Medium", "M"), ("Small", "S"))
                    if isinstance(pads, dict) and pads.get(k, pads.get(k.lower()))), None)
        distance = _value(row, "distanceToArrival")
        for key, value in (("n", name), ("s", system), ("t", _value(row, "type")), ("p", pad),
                           ("ls", round(distance, 1) if isinstance(distance, (int, float)) else None),
                           ("c", list(coords) if isinstance(coords, (list, tuple)) and len(coords) == 3 else None)):
            if value not in (None, "") and not existing.get(key):
                existing[key] = value
        if "M" in found:
            trader = economy_trader(row)
            if trader and existing.get("mt") in (None, "?"):
                existing["mt"] = trader
            elif not existing.get("mt"):
                existing["mt"] = "?"
        if "T" in found and not existing.get("tb"):
            existing["tb"] = "?"
        return existing != before

    def tags(self, system, row) -> list[str]:
        """Short codes for one station: E, M-R/M-M/M-E (or M), T-G/T-H (or T)."""
        result = []
        if self.engineer(system, row):
            result.append("E")
        entry = self.entry(system, row) or {}
        live = services(row)
        trader = entry.get("mt") or ("?" if "M" in live else None)
        if trader:
            trader = economy_trader(row) if trader == "?" else trader
            result.append("M-" + trader[0] if trader else "M")
        broker = entry.get("tb") or ("?" if "T" in live else None)
        if broker:
            result.append("T-" + broker[0] if broker != "?" else "T")
        return result

    def merge_download(self, payload) -> int:
        """Add a downloaded data file. Downloaded types fill unknowns; local finds are kept."""
        if not isinstance(payload, dict) or payload.get("version") != DATA_VERSION \
                or not isinstance(payload.get("stations"), dict):
            raise ValueError("Unrecognised station data file")
        added = 0
        for key, incoming in payload["stations"].items():
            if not isinstance(incoming, dict) or not incoming.get("n") or not incoming.get("s"):
                continue
            existing = self.data["stations"].get(str(key))
            if existing is None:
                name_key = self._names.get((_norm(incoming["s"]), _norm(incoming["n"])))
                if name_key and name_key.startswith("name:"):
                    existing = self.data["stations"].pop(name_key)   # promote a name-only find to its market ID
                    self.data["stations"][str(key)] = existing
            if existing is None:
                self.data["stations"][str(key)] = dict(incoming)
                added += 1
            else:
                for k, v in incoming.items():
                    if v not in (None, "") and existing.get(k) in (None, "", "?"):
                        existing[k] = v
            self._names[(_norm(incoming["s"]), _norm(incoming["n"]))] = str(key)
        self.data["downloaded"] = str(payload.get("built") or "yes")
        return added


def label(tags: list[str], symbols: bool = True) -> str:
    """Caption prefix such as '⚙(E) ⇄(M-R) '."""
    return "".join((GLYPHS[t[0]] if symbols else "") + "(" + t + ") " for t in tags)
