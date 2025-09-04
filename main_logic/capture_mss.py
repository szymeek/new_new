# -*- coding: utf-8 -*-
"""
Fast foreground capture using MSS for a given client-area bbox (screen coords).
Requires: mss, numpy, opencv-python
"""

from __future__ import annotations

import time
from typing import Tuple

import numpy as np

try:
    import mss
except ImportError as e:
    raise SystemExit("mss is required: pip install mss") from e

try:
    import cv2
except ImportError as e:
    raise SystemExit("opencv-python is required: pip install opencv-python") from e


class MSSCapture:
    def __init__(self) -> None:
        self._sct = mss.mss()

    def grab(self, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        left, top, width, height = bbox
        monitor = {"left": left, "top": top, "width": width, "height": height}
        sct_img = self._sct.grab(monitor)
        frame = np.asarray(sct_img, dtype=np.uint8)[..., :3]  # BGRA->BGR
        return frame

    def benchmark(self, bbox: Tuple[int, int, int, int], seconds: float = 3.0) -> float:
        t0 = time.perf_counter()
        frames = 0
        while (time.perf_counter() - t0) < seconds:
            _ = self.grab(bbox)
            frames += 1
        elapsed = time.perf_counter() - t0
        return frames / elapsed if elapsed > 0 else 0.0
