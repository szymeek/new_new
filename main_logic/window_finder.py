# -*- coding: utf-8 -*-
"""
Window discovery and client-area bbox computation for MTA: San Andreas.
Exports: WindowInfo, find_window, ensure_foreground, get_capture_bbox
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Tuple, List, Optional

try:
    import win32con
    import win32gui
    import win32process
except ImportError as e:
    raise SystemExit("pywin32 is required: pip install pywin32") from e

from ctypes import windll, byref, wintypes

__all__ = ["WindowInfo", "find_window", "ensure_foreground", "get_capture_bbox"]

@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    is_visible: bool
    is_minimized: bool
    client_bbox: Tuple[int, int, int, int]  # left, top, width, height (screen coords)

def _set_dpi_aware() -> None:
    try:
        windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def _get_client_rect_screen(hwnd: int) -> Tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not windll.user32.GetClientRect(hwnd, byref(rect)):
        raise RuntimeError("GetClientRect failed")
    pt_ul = wintypes.POINT(rect.left, rect.top)
    pt_br = wintypes.POINT(rect.right, rect.bottom)
    if not windll.user32.ClientToScreen(hwnd, byref(pt_ul)):
        raise RuntimeError("ClientToScreen(ul) failed")
    if not windll.user32.ClientToScreen(hwnd, byref(pt_br)):
        raise RuntimeError("ClientToScreen(br) failed")
    left = int(pt_ul.x)
    top = int(pt_ul.y)
    width = int(pt_br.x - pt_ul.x)
    height = int(pt_br.y - pt_ul.y)
    return left, top, width, height

def _is_minimized(hwnd: int) -> bool:
    return bool(win32gui.IsIconic(hwnd))

def _is_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))

def _get_pid(hwnd: int) -> int:
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return int(pid)

def _enum_windows() -> List[int]:
    hwnds: List[int] = []
    def _cb(h, _):
        hwnds.append(int(h))
        return True
    win32gui.EnumWindows(_cb, None)
    return hwnds

def _match_title(hwnd: int, needle: str) -> bool:
    try:
        title = win32gui.GetWindowText(hwnd) or ""
        return needle.lower() in title.lower()
    except Exception:
        return False

def find_window(title_contains: str = "MTA: San Andreas") -> Optional[WindowInfo]:
    """
    Locate a top-level window whose title contains the given substring.
    Prefer a visible, non-minimized window. Returns WindowInfo or None.
    """
    _set_dpi_aware()
    all_hwnds: List[int] = _enum_windows()
    matches: List[int] = [h for h in all_hwnds if _match_title(h, title_contains)]
    if not matches:
        return None

    # Build filtered candidates; select exactly one element for hwnd
    usable: List[int] = [h for h in matches if _is_visible(h) and not _is_minimized(h)]
    hwnd: int = (usable[0] if len(usable) > 0 else matches[0])

    title: str = win32gui.GetWindowText(hwnd) or title_contains
    visible: bool = _is_visible(hwnd)
    minimized: bool = _is_minimized(hwnd)
    try:
        bbox = _get_client_rect_screen(hwnd)
    except Exception:
        bbox = (0, 0, 0, 0)

    return WindowInfo(
        hwnd=hwnd,
        title=title,
        pid=_get_pid(hwnd),
        is_visible=visible,
        is_minimized=minimized,
        client_bbox=bbox,
    )

def ensure_foreground(hwnd: int, retries: int = 5, sleep_s: float = 0.05) -> bool:
    """
    Attempt to bring a window to foreground. Returns True on success.
    """
    try:
        for _ in range(retries):
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(sleep_s)
            if win32gui.GetForegroundWindow() == hwnd:
                return True
    except Exception:
        return False
    return False

def get_capture_bbox(info: WindowInfo) -> Tuple[int, int, int, int]:
    """
    Return the client-area bbox in screen coordinates (left, top, width, height).
    """
    l, t, w, h = info.client_bbox
    if w <= 0 or h <= 0:
        raise RuntimeError("Invalid client bbox; is the window minimized or unavailable?")
    return l, t, w, h
