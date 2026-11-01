# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Notes for (N) Tools: a small list of text notes saved as one JSON file. No tkinter here."""
from __future__ import annotations

import json
import os
import tempfile
import time

TITLE_CHARS = 26


class Notes:
    def __init__(self, path: str) -> None:
        self.path = path
        self.items: list[dict] = []
        self.current = 0
        self.load()

    # ------------------------------------------------------------------ storage
    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            data = {}
        items = data.get("notes") if isinstance(data, dict) else None
        self.items = [{"text": str(item.get("text", "")), "stamp": float(item.get("stamp") or 0)}
                      for item in (items or []) if isinstance(item, dict)]
        if not self.items:
            self.items = [{"text": "", "stamp": time.time()}]
        try:
            self.current = int(data.get("current", 0)) if isinstance(data, dict) else 0
        except (TypeError, ValueError):
            self.current = 0
        self.current = min(max(0, self.current), len(self.items) - 1)

    def save(self) -> bool:
        folder = os.path.dirname(self.path)
        try:
            os.makedirs(folder, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix="notes_", suffix=".tmp", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"notes": self.items, "current": self.current}, stream, ensure_ascii=False)
            for attempt in range(5):
                try:
                    os.replace(temporary, self.path)
                    return True
                except PermissionError:
                    time.sleep(0.1 * (attempt + 1))
            os.unlink(temporary)
        except OSError:
            pass
        return False

    # ------------------------------------------------------------------ editing
    @property
    def text(self) -> str:
        return self.items[self.current]["text"]

    def set_text(self, text: str) -> None:
        text = text.rstrip("\n")
        if text != self.items[self.current]["text"]:
            self.items[self.current].update(text=text, stamp=time.time())

    def new(self) -> None:
        """Add a blank note after the last one and move to it (an empty last note is reused, not duplicated)."""
        if not self.items[-1]["text"].strip():
            self.current = len(self.items) - 1
            return
        self.items.append({"text": "", "stamp": time.time()})
        self.current = len(self.items) - 1

    def delete(self) -> None:
        """Remove the shown note. The last remaining note is cleared rather than removed."""
        if len(self.items) == 1:
            self.items[0] = {"text": "", "stamp": time.time()}
            self.current = 0
            return
        del self.items[self.current]
        self.current = min(self.current, len(self.items) - 1)

    def goto(self, index: int) -> None:
        self.current = min(max(0, index), len(self.items) - 1)

    def step(self, direction: int) -> None:
        self.current = (self.current + direction) % len(self.items)

    # ------------------------------------------------------------------ display
    def title(self, index: int | None = None) -> str:
        text = self.items[self.current if index is None else index]["text"]
        for line in text.splitlines():
            if line.strip():
                line = line.strip()
                return line if len(line) <= TITLE_CHARS else line[:TITLE_CHARS - 1].rstrip() + "…"
        return "New note"

    def position(self) -> str:
        return f"{self.current + 1} of {len(self.items)}"
