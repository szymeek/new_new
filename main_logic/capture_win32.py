# -*- coding: utf-8 -*-
"""
Occlusion-tolerant capture using Win32 PrintWindow on the client area.
Works for many (not all) windows even when occluded; may be slower on Win11.
Requires: pywin32, numpy, opencv-python
"""

from __future__ import annotations

from typing import Tuple
import numpy as np

try:
    import win32gui
    import win32ui
    import win32con
except ImportError as e:
    raise SystemExit("pywin32 is required: pip install pywin32") from e

try:
    import cv2
except ImportError as e:
    raise SystemExit("opencv-python is required: pip install opencv-python") from e

from ctypes import windll, byref, wintypes


class Win32ClientCapture:
    def __init__(self, hwnd: int) -> None:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        self.hwnd = hwnd

    def _client_size(self) -> Tuple[int, int]:
        rect = wintypes.RECT()
        if not windll.user32.GetClientRect(self.hwnd, byref(rect)):
            raise RuntimeError("GetClientRect failed")
        w = int(rect.right - rect.left)
        h = int(rect.bottom - rect.top)
        return w, h

    def grab(self) -> np.ndarray:
        w, h = self._client_size()
        if w <= 0 or h <= 0:
            raise RuntimeError("Zero-sized client area; minimized?")

        hwnd_dc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
        save_dc.SelectObject(bitmap)

        # Try multiple PrintWindow flags; some apps behave differently
        result = windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 3)
        if result != 1:
            result = windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 2)
            if result != 1:
                result = windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 1)

        bmpinfo = bitmap.GetInfo()
        bmpbytes = bitmap.GetBitmapBits(True)
        img = np.frombuffer(bmpbytes, dtype=np.uint8)
        img = img.reshape((bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4))[..., :3]  # BGRA->BGR
        img = np.ascontiguousarray(img)

        # Cleanup GDI objects
        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(self.hwnd, hwnd_dc)

        if result != 1:
            raise RuntimeError(f"PrintWindow failed or returned {result}")

        return img
