# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Windows scan-code input while the real Elite executable is foreground."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import os
import time
from .commands import Cancelled

# Explicit 32-bit Win32 fields also make the structure testable on Linux.
class KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", ctypes.c_uint32),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]
class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]
class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyboardInput), ("mi", MouseInput), ("hi", HardwareInput)]
class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("data", InputUnion)]

class WindowsInput:
    def __init__(self):
        self.user = self.kernel = None
        if os.name != "nt":
            return
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.user.SendInput.restype = wintypes.UINT
        self.user.GetAsyncKeyState.argtypes, self.user.GetAsyncKeyState.restype = [ctypes.c_int], ctypes.c_short
        self.user.MapVirtualKeyW.argtypes, self.user.MapVirtualKeyW.restype = [wintypes.UINT, wintypes.UINT], wintypes.UINT
    def is_game_foreground(self):
        if self.user is None:
            return False
        window, pid = self.user.GetForegroundWindow(), wintypes.DWORD()
        if not window or not self.user.GetWindowThreadProcessId(window, ctypes.byref(pid)):
            return False
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return False
            return os.path.basename(buffer.value).casefold() == "elitedangerous64.exe"
        finally:
            self.kernel.CloseHandle(handle)
    @staticmethod
    def packet(key, up):
        flags = 8 | (1 if key.extended else 0) | (2 if up else 0)
        return Input(1, InputUnion(ki=KeyboardInput(0, key.scan, flags, 0, 0)))
    def _send(self, key, up):
        packet = self.packet(key, up)
        if self.user.SendInput(1, ctypes.byref(packet), ctypes.sizeof(Input)) != 1:
            raise OSError("Windows did not accept input. Check that Elite and EDMC run at the same privilege level.")
    def tap(self, keys, hold, cancel):
        if self.user is None:
            raise OSError("Game input requires Windows")
        for key in keys:
            vk = self.user.MapVirtualKeyW(key.scan | (0xe000 if key.extended else 0), 3)
            if vk and self.user.GetAsyncKeyState(vk) & 0x8000:
                raise RuntimeError("A macro key is already held: " + key.name)
        pressed = []
        try:
            for key in keys:
                if cancel.is_set() or not self.is_game_foreground():
                    raise Cancelled("Macro stopped before the next key")
                pressed.append(key)
                self._send(key, False)
                if key is not keys[-1] and cancel.wait(.02):
                    raise Cancelled("Macro cancelled")
            deadline = time.monotonic() + hold
            while time.monotonic() < deadline:
                if cancel.is_set() or not self.is_game_foreground():
                    raise Cancelled("Macro stopped; held keys released")
                cancel.wait(min(.02, max(0., deadline - time.monotonic())))
        finally:
            error = None
            for key in reversed(pressed):
                try:
                    self._send(key, True)
                except OSError as exc:
                    error = exc
            if error:
                raise error
