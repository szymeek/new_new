# -*- coding: utf-8 -*-
"""
Runner to capture the MTA window using MSS (fast, foreground) or Win32 (occlusion-tolerant).
Usage:
  python -m main_logic.capture_runner --backend mss --save screenshots/test_mss.png
  python -m main_logic.capture_runner --backend mss --preview
  python -m main_logic.capture_runner --backend win32 --preview
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2
except ImportError as e:
    raise SystemExit("opencv-python is required: pip install opencv-python") from e

from .window_finder import find_window, ensure_foreground, get_capture_bbox, WindowInfo
from .capture_mss import MSSCapture
from .capture_win32 import Win32ClientCapture


def _overlay_fps(frame: np.ndarray, fps: float, backend: str, title: str) -> np.ndarray:
    out = frame.copy()
    text = f"{backend} | {fps:.1f} FPS | {title}"
    cv2.putText(out, text, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
    return out

def run(backend: str, title_contains: str, preview: bool, save_path: Optional[str]) -> None:
    info: Optional[WindowInfo] = find_window(title_contains=title_contains)
    if info is None:
        raise SystemExit(f"Window not found containing title: {title_contains}")

    if backend == "mss":
        if not ensure_foreground(info.hwnd):
            print("Warning: could not force foreground; MSS requires unobstructed window.")
        bbox = get_capture_bbox(info)
        cap = MSSCapture()
        if save_path:
            frame = cap.grab(bbox)
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(save_path, frame)
            print(f"Saved: {save_path}")
            return
        if preview:
            t0 = time.perf_counter()
            frames = 0
            while True:
                frame = cap.grab(bbox)
                frames += 1
                elapsed = time.perf_counter() - t0
                fps = frames / elapsed if elapsed > 0 else 0.0
                disp = _overlay_fps(frame, fps, "MSS", info.title)
                cv2.imshow("Capture Preview", disp)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cv2.destroyAllWindows()
        else:
            frame = cap.grab(bbox)
            print(f"Captured frame: {frame.shape[11]}x{frame.shape} via MSS")
    elif backend == "win32":
        cap = Win32ClientCapture(info.hwnd)
        if save_path:
            frame = cap.grab()
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(save_path, frame)
            print(f"Saved: {save_path}")
            return
        if preview:
            t0 = time.perf_counter()
            frames = 0
            while True:
                frame = cap.grab()
                frames += 1
                elapsed = time.perf_counter() - t0
                fps = frames / elapsed if elapsed > 0 else 0.0
                disp = _overlay_fps(frame, fps, "Win32", info.title)
                cv2.imshow("Capture Preview", disp)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cv2.destroyAllWindows()
        else:
            frame = cap.grab()
            print(f"Captured frame: {frame.shape[11]}x{frame.shape} via Win32")
    else:
        raise SystemExit("Unknown backend. Use --backend mss or --backend win32")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["mss", "win32"], default="mss")
    ap.add_argument("--title", default="MTA: San Andreas")
    ap.add_argument("--save", default=None)
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    run(backend=args.backend, title_contains=args.title, preview=args.preview, save_path=args.save)

if __name__ == "__main__":
    main()
