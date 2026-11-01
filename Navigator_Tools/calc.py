# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""The arithmetic behind (N) Tools: a safe expression calculator and the game calculations.

No tkinter in here, so everything can be tested on its own.
"""
from __future__ import annotations

import ast
import math
import operator
import re
from typing import Callable

LS_PER_LY = 31_557_600.0          # one light-year in light-seconds (299,792,458 m/s x 365.25 days)
MAX_POWER = 1000

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalcError(ValueError):
    """The text is not a sum the calculator can do."""


def evaluate(text: str) -> float:
    """Evaluate a typed or keypad expression (+ - * / % ** and brackets) without running arbitrary code."""
    cleaned = (text or "").replace("×", "*").replace("÷", "/").replace("−", "-").replace(",", "").strip()
    cleaned = re.sub(r"(?<=[0-9.)\s])[xX](?=[0-9.(\s+-])", "*", cleaned)      # 3x4 and 3 X 4 mean times
    if not cleaned:
        raise CalcError("empty")
    # 50% means 0.5 and 200+10% means 200+10/100 - keep it simple: a trailing % is divide-by-100.
    cleaned = cleaned.replace("%", "/100")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as error:
        raise CalcError("syntax") from error
    value = _walk(tree.body)
    if isinstance(value, complex) or math.isnan(value) or math.isinf(value):
        raise CalcError("not a number")
    return value


def _walk(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _walk(node.left), _walk(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise CalcError("too big")
        try:
            return _BINARY[type(node.op)](left, right)
        except ZeroDivisionError as error:
            raise CalcError("divide by zero") from error
        except OverflowError as error:
            raise CalcError("too big") from error
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_walk(node.operand))
    raise CalcError("unsupported")


def fmt(value: float, places: int = 2) -> str:
    """A tidy number: thousands separators, at most `places` decimals, no trailing zeros."""
    if value is None:
        return ""
    if abs(value) >= 1e15 or (value != 0 and abs(value) < 1e-9):
        return f"{value:.6g}"
    text = f"{value:,.{places}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def fmt_calc(value: float) -> str:
    """The basic calculator's display: up to 10 decimals, no separators (so the result can be used again)."""
    if float(value).is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.10f}".rstrip("0").rstrip(".") if abs(value) < 1e15 else f"{value:.8g}"


def duration(seconds: float) -> str:
    seconds = int(round(max(0.0, seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours}:{minutes:02d}:{secs:02d}"


def number(values: dict, key: str) -> float | None:
    """A field's value, or None when it is blank or not a number. Sums such as 12*3 are accepted too."""
    text = str(values.get(key, "")).strip()
    if not text:
        return None
    try:
        return float(evaluate(text))
    except CalcError:
        return None


# --------------------------------------------------------------------------- game calculations
# Each entry: (name, [(key, label)], compute(values) -> [(label, text)]).  A result row is only shown when it can be worked out.
def _jumps(values: dict) -> list[tuple[str, str]]:
    distance, jump_range = number(values, "distance"), number(values, "range")
    per_jump, tank = number(values, "fuel"), number(values, "tank")
    rows: list[tuple[str, str]] = []
    if distance is None or jump_range is None or jump_range <= 0 or distance < 0:
        return rows
    jumps = max(1, math.ceil(distance / jump_range - 1e-9)) if distance > 0 else 0
    rows.append(("Jumps", fmt(jumps, 0)))
    if per_jump is not None and per_jump >= 0:
        total = jumps * per_jump
        rows.append(("Fuel needed", fmt(total) + " t"))
        if tank is not None and tank > 0:
            rows.append(("Tanks of fuel", fmt(total / tank)))
            rows.append(("Scoop or refuel stops", fmt(max(0, math.ceil(total / tank - 1e-9) - 1), 0)))
    return rows


def _travel(values: dict) -> list[tuple[str, str]]:
    jumps, seconds = number(values, "jumps"), number(values, "seconds")
    extra = number(values, "stops") or 0.0
    stop_minutes = number(values, "stop_minutes") or 0.0
    if jumps is None or seconds is None or jumps < 0 or seconds < 0:
        return []
    total = jumps * seconds + max(0.0, extra) * max(0.0, stop_minutes) * 60
    rows = [("Total time", duration(total))]
    if jumps > 0:
        rows.append(("Average per jump", duration(total / jumps)))
    return rows


def _trade(values: dict) -> list[tuple[str, str]]:
    units, buy, sell = number(values, "units"), number(values, "buy"), number(values, "sell")
    if buy is None or sell is None:
        return []
    rows = [("Profit per unit", fmt(sell - buy) + " cr")]
    if buy > 0:
        rows.append(("Margin", fmt((sell - buy) / buy * 100, 1) + " %"))
    if units is not None and units >= 0:
        rows.insert(0, ("Total profit", fmt((sell - buy) * units) + " cr"))
        rows.append(("Total cost", fmt(buy * units) + " cr"))
    return rows


def _hourly(values: dict) -> list[tuple[str, str]]:
    credits, minutes = number(values, "credits"), number(values, "minutes")
    if credits is None or minutes is None or minutes <= 0:
        return []
    return [("Credits per hour", fmt(credits / minutes * 60) + " cr"), ("Credits per minute", fmt(credits / minutes) + " cr")]


def _mining(values: dict) -> list[tuple[str, str]]:
    tons, price, minutes = number(values, "tons"), number(values, "price"), number(values, "minutes")
    if tons is None or price is None:
        return []
    rows = [("Haul value", fmt(tons * price) + " cr")]
    if minutes is not None and minutes > 0:
        rows.append(("Credits per hour", fmt(tons * price / minutes * 60) + " cr"))
        rows.append(("Tons per hour", fmt(tons / minutes * 60)))
    return rows


def _light(values: dict) -> list[tuple[str, str]]:
    ly, ls = number(values, "ly"), number(values, "ls")
    rows: list[tuple[str, str]] = []
    if ly is not None:
        rows.append(("Light-seconds", fmt(ly * LS_PER_LY, 0) + " Ls"))
    if ls is not None:
        rows.append(("Light-years", fmt(ls / LS_PER_LY, 6) + " Ly"))
    return rows


GAME_CALCS: list[tuple[str, list[tuple[str, str]], Callable[[dict], list[tuple[str, str]]]]] = [
    ("Jumps and fuel", [("distance", "Distance (Ly)"), ("range", "Jump range (Ly)"), ("fuel", "Fuel per jump (t)"),
                        ("tank", "Fuel tank (t)")], _jumps),
    ("Travel time", [("jumps", "Jumps"), ("seconds", "Seconds per jump"), ("stops", "Refuel stops"),
                     ("stop_minutes", "Minutes per stop")], _travel),
    ("Trade profit", [("units", "Units"), ("buy", "Buy price (cr)"), ("sell", "Sell price (cr)")], _trade),
    ("Earnings per hour", [("credits", "Credits earned"), ("minutes", "Minutes taken")], _hourly),
    ("Mining haul", [("tons", "Tons mined"), ("price", "Price per ton (cr)"), ("minutes", "Minutes taken")], _mining),
    ("Ly and Ls", [("ly", "Light-years (Ly)"), ("ls", "Light-seconds (Ls)")], _light),
]
MAX_FIELDS = max(len(fields) for _name, fields, _compute in GAME_CALCS)
MAX_RESULTS = 4


def compute(name: str, values: dict) -> list[tuple[str, str]]:
    for title, _fields, function in GAME_CALCS:
        if title == name:
            return function(values)[:MAX_RESULTS]
    return []
