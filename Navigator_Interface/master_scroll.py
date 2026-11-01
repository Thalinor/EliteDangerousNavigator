# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Master scroll for EDMC's main window (Dark and Transparent themes only).

When the plugins are expanded so far that EDMC's window is taller than the screen, EDMC cannot be shrunk and the bottom
runs off the screen. This keeps the window within the screen and moves EDMC's content up and down inside it, with a thin
glass-like sliver (the Highlighted Text colour) on one edge. It exists only while it is needed: when the content fits,
EDMC lays itself out exactly as before.

How: EDMC's content frame is normally gridded into the main window, which sizes itself to fit it. While the content is too
tall the frame is placed instead (so it no longer sizes the window), the window is held to the screen height, and the frame
is moved by -offset. The window clips what is outside it. Everything is undone as soon as the content fits again, or if
anything goes wrong.
"""
from __future__ import annotations

import sys
import tkinter as tk
from typing import Any, Callable

BAR_WIDTH = 3            # the sliver: pencil thin, and the whole of what is drawn (no padding around it)

GAP = BAR_WIDTH           # clear space between the bar and the plugins' text (a single bar width)
MIN_THUMB = 56
MIN_VIEW = 160           # never shrink the window below this when scrolling
WHEEL_STEP = 48
SWIPE_START = 8          # px of finger / mouse travel before a press becomes a scroll (less is still a tap)
HIDE_MS = 1400            # the bar fades away this long after the last scroll
EDGE_ZONE = 40           # near the bar's edge a drag always scrolls the whole window, even over a plugin's own scroller
OWN_SCROLL = ('Canvas', 'Text', 'Listbox', 'Treeview')
NEVER_DRAG = ('Scrollbar', 'TScrollbar', 'Scale', 'TScale', 'Entry', 'TEntry', 'TCombobox', 'Spinbox')


class MasterScroll:
    def __init__(self, root: tk.Misc, frame: Callable[[], tk.Misc | None], colour: Callable[[], str],
                 side: Callable[[], str], logger: Any, grip_height: int = 11,
                 wanted: Callable[[], int | None] | None = None,
                 bar: Callable[[], str] | None = None) -> None:
        """wanted: the window height the user chose (dragged to, or locked), or None when they have not chosen one.
        bar: 'auto' (the bar shows only while scrolling) or 'never' (scrolling works, no bar is drawn)."""
        self.root, self._frame, self._colour, self._side, self.logger = root, frame, colour, side, logger
        self._wanted = wanted or (lambda: None)
        self._bar = bar or (lambda: "auto")
        self._shown = False
        self._hide_timer = None
        self._gutter: tk.Frame | None = None
        self.grip = grip_height
        self.active = False
        self.broken = False
        self.offset = 0
        self._need = 0
        self._saved_grid: dict | None = None
        self._saved_min: tuple | None = None
        self._canvas: tk.Canvas | None = None
        self._drag: tuple[int, int] | None = None
        self._logged = False
        self._bound = False
        self._dead = False
        self._touch: dict | None = None

    @property
    def gutter(self) -> int:
        """Pixels kept clear along the bar's edge while scrolling is on: the bar and a gap. None when no bar is ever drawn."""
        return 0 if self._bar() == "never" else BAR_WIDTH + GAP

    def _backdrop(self, view: int) -> str:
        """What the bar and its gap sit on: the transparent key colour in Transparent (so it is truly see-through),
        otherwise the colour of the panel beside it."""
        try:
            key = str(self.root.attributes("-transparentcolor"))
            if key:
                return key
        except tk.TclError:
            pass
        try:
            left = self._side() == "left"
            x = self.root.winfo_rootx() + (self.gutter + 6 if left else self.root.winfo_width() - self.gutter - 6)
            near = self.root.winfo_containing(x, self.root.winfo_rooty() + view // 2)
        except tk.TclError:
            near = None
        for candidate in (near, self._frame()):
            try:
                colour = str(candidate.cget("background"))
                if colour:
                    return colour
            except (tk.TclError, AttributeError):
                continue
        return "black"

    # ----------------------------------------------------------------------------------------- measuring
    def _limit(self) -> int:
        """The tallest the window may be: from its top edge to the bottom of the usable screen (above the taskbar)."""
        bottom = self.root.winfo_screenheight() - 48
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):    # SPI_GETWORKAREA
                    bottom = rect.bottom
            except Exception:
                pass
        top = max(0, self.root.winfo_rooty())
        return max(MIN_VIEW, bottom - top)

    def _usable(self) -> tk.Misc | None:
        frame = self._frame()
        try:
            if frame is None or frame is self.root or frame.master is not self.root:
                return None
            if frame.winfo_manager() not in ("grid", "place"):
                return None
        except tk.TclError:
            return None
        return frame

    def _dump(self, frame: tk.Misc) -> None:
        """One diagnostic line per window child, to the EDMC log, so a problem on another machine can be understood."""
        if self._logged:
            return
        self._logged = True
        try:
            parts = []
            for child in self.root.winfo_children():
                parts.append(f"{child.winfo_name()}({child.winfo_class()},{child.winfo_manager()},"
                             f"{child.winfo_reqwidth()}x{child.winfo_reqheight()})")
            self.logger.info("Master scroll: window %sx%s at y=%s, children: %s; frame %sx%s", self.root.winfo_width(),
                             self.root.winfo_height(), self.root.winfo_rooty(), ", ".join(parts), frame.winfo_reqwidth(),
                             frame.winfo_reqheight())
        except tk.TclError:
            pass

    # ----------------------------------------------------------------------------------------- the main entry
    def sync(self, enabled: bool) -> None:
        if self.broken:
            return
        try:
            self._sync(enabled)
        except Exception:
            self.logger.exception("Master scroll failed; switching it off for this session")
            self.broken = True
            try:
                self.deactivate()
            except Exception:
                self.logger.exception("Master scroll could not restore the window layout")

    def _sync(self, enabled: bool) -> None:
        frame = self._usable()
        if (not enabled or frame is None or not self.root.overrideredirect() or self.root.state() != "normal"):
            if self.active:
                self.deactivate()
            return
        self._dump(frame)
        need_h, need_w = frame.winfo_reqheight(), frame.winfo_reqwidth()
        limit = self._limit()
        wanted = self._wanted()
        # Needed when the content is taller than the screen, or taller than the window height the user chose.
        needed = need_h > limit or (wanted is not None and wanted < need_h - 1)
        if not self.active:
            if not needed:
                return
            self.activate(frame)
        elif not needed:
            self.deactivate()
            return
        self._need = need_h
        if self.root.minsize()[1] > MIN_VIEW:
            self.root.minsize(self.root.minsize()[0], MIN_VIEW)          # EDMC's theme pass resets it to the full height
        gutter = self.gutter
        width = max(self.root.winfo_width(), need_w + gutter)
        height = max(MIN_VIEW, min(limit, wanted if wanted is not None else self.root.winfo_height()))
        if self.root.winfo_height() != height or self.root.winfo_width() != width:
            self.root.geometry(f"{width}x{height}")
        view = height
        self.offset = max(0, min(self.offset, need_h - view))
        frame.place_configure(x=gutter if self._side() == "left" else 0, y=-self.offset, relwidth=1, width=-gutter, height=need_h)
        self._place_bar(view)

    # ----------------------------------------------------------------------------------------- on / off
    def activate(self, frame: tk.Misc) -> None:
        if frame.winfo_manager() == "grid":
            self._saved_grid = dict(frame.grid_info())
            self._saved_grid.pop("in", None)
            frame.grid_remove()
        self._saved_min = self.root.minsize()
        self.root.minsize(min(self._saved_min[0], self.root.winfo_width()), MIN_VIEW)
        frame.place(in_=self.root, x=0, y=0, relwidth=1, height=frame.winfo_reqheight(), anchor=tk.NW)
        self.active = True
        self.offset = 0
        if not self._bound:
            self.root.bind("<MouseWheel>", self._wheel, add="+")
            self.root.bind("<Motion>", self._motion, add="+")
            self.root.bind("<ButtonPress-1>", self._touch_press, add="+")
            self.root.bind("<B1-Motion>", self._touch_move, add="+")
            self.root.bind("<ButtonRelease-1>", self._touch_release, add="+")
            self._bound = True
        self._reveal()
        self.logger.info("Master scroll on: content %s px, window limit %s px", frame.winfo_reqheight(), self._limit())

    def deactivate(self) -> None:
        frame = self._frame()
        if self.active and frame is not None:
            try:
                frame.place_forget()
                if self._saved_grid:
                    frame.grid(**{key: value for key, value in self._saved_grid.items() if key != "in"})
                else:
                    frame.grid(sticky=tk.NSEW)
            except tk.TclError:
                pass
            if self._saved_min is not None:
                try:
                    self.root.minsize(1, 1)
                    self.root.minsize(*self._saved_min)
                except tk.TclError:
                    pass
            try:
                self.root.geometry("")          # hand the size back to EDMC
            except tk.TclError:
                pass
            self.logger.info("Master scroll off: the content fits")
        self.active = False
        self.offset = 0
        self._saved_grid = self._saved_min = None
        self._hide()
        if self._gutter is not None:
            self._gutter.place_forget()

    def shutdown(self) -> None:
        try:
            self.deactivate()
        except Exception:
            pass
        if self._canvas is not None:
            try:
                self._canvas.destroy()
            except tk.TclError:
                pass
            self._canvas = None
        self._cancel_hide()
        self._dead = True              # the bindings stay (unbinding would remove other plugins' too) but do nothing
        self._dead = False
        self._touch: dict | None = None

    # ----------------------------------------------------------------------------------------- scrolling
    def scroll_to(self, offset: float) -> None:
        frame = self._frame()
        if not self.active or frame is None:
            return
        view = self.root.winfo_height()
        offset = int(max(0, min(offset, self._need - view)))
        if offset != self.offset:
            self.offset = offset
            frame.place_configure(y=-offset)
        self._reveal()

    def _reveal(self) -> None:
        """Show the bar (it hides itself a moment after the last scroll)."""
        if self._dead or not self.active or self._bar() == "never":
            return
        self._shown = True
        self._place_bar(self.root.winfo_height())
        self._cancel_hide()
        self._hide_timer = self.root.after(HIDE_MS, self._hide_later)

    def _cancel_hide(self) -> None:
        if self._hide_timer is not None:
            try:
                self.root.after_cancel(self._hide_timer)
            except (tk.TclError, ValueError):
                pass
            self._hide_timer = None

    def _hide_later(self) -> None:
        self._hide_timer = None
        if self._drag is not None or self._touch and self._touch.get("swiping"):
            self._hide_timer = self.root.after(HIDE_MS, self._hide_later)       # still in use
            return
        self._hide()

    def _hide(self) -> None:
        self._cancel_hide()
        self._shown = False
        if self._canvas is not None:
            try:
                self._canvas.place_forget()
            except tk.TclError:
                pass

    def _motion(self, event: tk.Event) -> None:
        """Pointer near the bar's edge brings it into view, so it can be found and dragged."""
        if self._dead or not self.active or self._shown:
            return
        try:
            x = event.x_root - self.root.winfo_rootx()
            if (x <= EDGE_ZONE) if self._side() == "left" else (x >= self.root.winfo_width() - EDGE_ZONE):
                self._reveal()
        except tk.TclError:
            pass

    def _owns_drag(self, event: tk.Event) -> bool:
        """May a press here start a swipe that scrolls the whole window? Not on a bar or entry box, and not inside a plugin's
        own scrolling area (it scrolls itself) - except near the edge where the bar is."""
        try:
            width = self.root.winfo_width()
            x = event.x_root - self.root.winfo_rootx()
            if (x <= EDGE_ZONE) if self._side() == "left" else (x >= width - EDGE_ZONE):
                return True
            widget = event.widget
            while widget is not None and widget is not self.root:
                kind = widget.winfo_class()
                if kind in NEVER_DRAG:
                    return False
                if getattr(widget, "navigator_window_drag", False):
                    return False        # a header that moves the window
                if kind in OWN_SCROLL and widget is not self._canvas:
                    try:
                        if tuple(widget.yview()) != (0.0, 1.0):
                            return False
                    except (tk.TclError, ValueError, AttributeError):
                        pass
                widget = widget.master
        except tk.TclError:
            return False
        return True

    def _touch_press(self, event: tk.Event) -> None:
        self._touch = None
        if self._dead or not self.active or event.widget is self._canvas:
            return
        self._touch = {"y": event.y_root, "offset": self.offset, "ok": self._owns_drag(event), "swiping": False}

    def _touch_move(self, event: tk.Event) -> None:
        touch = self._touch
        if self._dead or not self.active or not touch or not touch["ok"]:
            return
        travel = touch["y"] - event.y_root                  # a finger moving up brings later content into view
        if not touch["swiping"] and abs(travel) >= SWIPE_START:
            touch["swiping"] = True
        if touch["swiping"]:
            self.scroll_to(touch["offset"] + travel)

    def _touch_release(self, _event: tk.Event) -> None:
        self._touch = None

    def _wheel(self, event: tk.Event) -> None:
        if self._dead:
            return
        if not self.active:
            return
        widget = event.widget
        up = event.delta > 0
        try:
            if widget.winfo_class() in ("Canvas", "Text", "Listbox", "Treeview"):
                low, high = widget.yview()
                if (up and low > 0) or (not up and high < 1):
                    return                      # a scrolling area under the pointer keeps the wheel until it hits its end
        except (tk.TclError, ValueError, AttributeError):
            pass
        self.scroll_to(self.offset + (-WHEEL_STEP if up else WHEEL_STEP))

    # ----------------------------------------------------------------------------------------- the sliver
    def _place_bar(self, view: int) -> None:
        if self._canvas is None or not self._canvas.winfo_exists():
            self._canvas = tk.Canvas(self.root, highlightthickness=0, borderwidth=0, cursor="sb_v_double_arrow")
            self._canvas.bind("<ButtonPress-1>", self._press)
            self._canvas.bind("<B1-Motion>", self._move)
            self._canvas.bind("<ButtonRelease-1>", self._release)
        canvas = self._canvas
        left = self._side() == "left"
        transparent = ""
        try:
            transparent = str(self.root.attributes("-transparentcolor"))
        except tk.TclError:
            pass
        width = BAR_WIDTH          # nothing beside the bar, so it never covers a plugin's buttons
        background = self._backdrop(view)
        canvas.configure(background=background, width=width, height=max(1, view - self.grip))
        self._place_gutter(view, background)
        if not self._shown or self._bar() == "never":
            canvas.place_forget()
            return
        canvas.place(in_=self.root, relx=0 if left else 1, x=0, y=0, anchor=tk.NW if left else tk.NE,
                     width=width, height=max(1, view - self.grip))
        tk.Misc.lift(canvas)               # Canvas.lift would mean "raise a drawn item"
        self._draw(view)

    def _place_gutter(self, view: int, colour: str) -> None:
        """The clear strip between the bar and the plugins, in the backdrop colour (see-through in Transparent)."""
        gutter = self.gutter
        if gutter <= 0:
            if self._gutter is not None:
                self._gutter.place_forget()
            return
        if self._gutter is None or not self._gutter.winfo_exists():
            self._gutter = tk.Frame(self.root, highlightthickness=0, borderwidth=0)
        left = self._side() == "left"
        self._gutter.configure(background=colour)
        self._gutter.place(in_=self.root, relx=0 if left else 1, x=0, y=0, anchor=tk.NW if left else tk.NE,
                           width=gutter, height=max(1, view - self.grip))
        tk.Misc.lower(self._gutter)

    def _geometry(self, view: int) -> tuple[float, float, float]:
        track = max(1, view - self.grip)
        span = max(1, self._need - view)
        thumb = max(MIN_THUMB, min(track, track * view / max(1, self._need)))
        top = (track - thumb) * (self.offset / span)
        return track, thumb, top

    def _draw(self, view: int) -> None:
        canvas = self._canvas
        if canvas is None or not self.active:
            return
        canvas.delete("all")
        track, thumb, top = self._geometry(view)
        width = int(canvas.cget("width"))
        left = self._side() == "left"
        edge = 0 if left else width - BAR_WIDTH
        centre = edge + BAR_WIDTH / 2
        colour = self._colour()
        end = thumb * 0.34                                          # the longer the bar, the more ticks
        # Solid middle, then dashes that thin out and spread apart toward each end (the "granulated" ends).
        canvas.create_rectangle(edge, top + end, edge + BAR_WIDTH, top + thumb - end, fill=colour, outline="")
        for from_top in (True, False):
            position = 0.0
            while position < end - 1:
                fraction = 1 - position / end                       # 1 at the solid part, 0 at the very tip
                gap = 1 + 8 * (1 - fraction) ** 1.3
                half = max(0.5, BAR_WIDTH / 2 * (0.35 + 0.65 * fraction))
                y = top + end - position - 2 if from_top else top + thumb - end + position
                canvas.create_rectangle(centre - half, y, centre + half, y + 2, fill=colour, outline="")
                position += 2 + gap

    def _press(self, event: tk.Event) -> str:
        view = self.root.winfo_height()
        track, thumb, top = self._geometry(view)
        if top <= event.y <= top + thumb:
            self._drag = (event.y, self.offset)
        else:
            # A tap on the empty track moves the thumb's centre there.
            span = max(1, self._need - view)
            ratio = (event.y - thumb / 2) / max(1, track - thumb)
            self.scroll_to(max(0.0, min(1.0, ratio)) * span)
            self._drag = (event.y, self.offset)
        return "break"

    def _move(self, event: tk.Event) -> str:
        if self._drag is None:
            return "break"
        view = self.root.winfo_height()
        track, thumb, _ = self._geometry(view)
        span = max(1, self._need - view)
        start_y, start_offset = self._drag
        self.scroll_to(start_offset + (event.y - start_y) * span / max(1, track - thumb))
        return "break"

    def _release(self, _event: tk.Event) -> str:
        self._drag = None
        return "break"
