# -*- coding: utf-8 -*-
"""
Global key listener that triggers a screenshot of the MTA client area
upon Alt, Q, or E keypress. Thread-safe MSS implementation.
Saves only first 3 screenshots as 26x26 crops at specific coordinates.
Screenshots: Alt=1, Q/E=2, Q/E=3 (position 4 is skipped)
Press ESC to quit.

to run:
python -m main_logic.hotkey_capture --title "MTA: San Andreas" --delay-ms 500 --save-dir screenshots
"""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2
except ImportError as e:
    raise SystemExit("opencv-python is required: pip install opencv-python") from e

try:
    from pynput import keyboard
except ImportError as e:
    raise SystemExit("pynput is required: pip install pynput") from e

try:
    import mss
except ImportError as e:
    raise SystemExit("mss is required: pip install mss") from e

from .window_finder import find_window, get_capture_bbox, ensure_foreground, WindowInfo


class KeypressCapture:
    def __init__(
        self,
        title_contains: str,
        save_dir: str,
        post_press_delay_ms: int = 0,
        bring_foreground: bool = True,
    ) -> None:
        self.title_contains = title_contains
        self.post_press_delay_ms = max(0, int(post_press_delay_ms))
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        info = find_window(title_contains=self.title_contains)
        if info is None:
            raise SystemExit(f"Window not found containing title: {self.title_contains}")
        self.info: WindowInfo = info

        if bring_foreground:
            ensure_foreground(self.info.hwnd)

        self._lock = threading.Lock()
        self._counter = 0
        self._running = True

        # Cycle tracking: Alt=1, Q/E=2, Q/E=3, position 4 is skipped
        self._cycle_position = 0
        self._total_screenshots = 0

        # Crop coordinates for each position (26x26 crops)
        self._crop_coords = {
            1: (39, 943),   # Alt position
            2: (97, 943),   # First Q/E position  
            3: (155, 943),  # Second Q/E position
        }
        self._crop_size = 26

        self._last_ts = {"alt": 0.0, "q": 0.0, "e": 0.0}
        self._debounce_s = 0.08

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _get_cycle_position(self, keyname: str) -> int:
        """Get the position number (1-3) for this keypress in the current cycle"""
        with self._lock:
            if keyname == "alt":
                # Alt always starts a new cycle at position 1
                self._cycle_position = 1
            else:
                # Q/E increment position, but only save positions 1-3
                self._cycle_position += 1
                if self._cycle_position > 4:
                    self._cycle_position = 2  # Reset to 2 if no Alt pressed
            
            return self._cycle_position

    def _safe_grab(self) -> Optional[np.ndarray]:
        """Thread-safe capture using fresh MSS context manager"""
        try:
            bbox = get_capture_bbox(self.info)
            with mss.mss() as sct:
                monitor = {
                    "left": bbox[0], 
                    "top": bbox[1], 
                    "width": bbox[2], 
                    "height": bbox[3]
                }
                screenshot = sct.grab(monitor)
            frame = np.asarray(screenshot, dtype=np.uint8)[..., :3]
            return frame
        except Exception as e:
            print(f"[warn] capture failed: {e}")
            return None

    def _crop_frame(self, frame: np.ndarray, cycle_pos: int) -> Optional[np.ndarray]:
        """Crop frame to 26x26 at specified coordinates"""
        if cycle_pos not in self._crop_coords:
            return None
        
        x, y = self._crop_coords[cycle_pos]
        size = self._crop_size
        
        # Check bounds
        if (y + size > frame.shape[0]) or (x + size > frame.shape[1]):
            print(f"[warn] crop coordinates ({x}, {y}) + {size}x{size} exceed frame bounds {frame.shape}")
            return None
        
        # Crop using numpy slicing: frame[y:y+height, x:x+width]
        cropped = frame[y:y+size, x:x+size]
        return cropped

    def _save_frame(self, frame: np.ndarray, keyname: str, cycle_pos: int) -> str:
        ts = self._now_ms()
        with self._lock:
            self._total_screenshots += 1
            total_idx = self._total_screenshots
        
        # Filename: {cycle_position}_{keyname}_{timestamp}_{total_index}.png
        fname = f"{cycle_pos}_{keyname}_{ts}_{total_idx:04d}.png"
        path = self.save_dir / fname
        cv2.imwrite(str(path), frame)
        return str(path)

    def _handle_keypress(self, keyname: str) -> None:
        now = time.perf_counter()
        last = self._last_ts.get(keyname, 0.0)
        if (now - last) < self._debounce_s:
            return
        self._last_ts[keyname] = now

        if self.post_press_delay_ms > 0:
            time.sleep(self.post_press_delay_ms / 1000.0)

        # Get cycle position before capture
        cycle_pos = self._get_cycle_position(keyname)
        
        # Skip position 4 - don't save anything
        if cycle_pos == 4:
            print(f"[skip] {keyname} (pos {cycle_pos}) - not saving position 4")
            return
        
        # Capture full frame
        frame = self._safe_grab()
        if frame is None:
            print(f"[warn] no frame for key={keyname}")
            return
        
        # Crop to 26x26 at specified coordinates
        cropped = self._crop_frame(frame, cycle_pos)
        if cropped is None:
            print(f"[warn] crop failed for key={keyname} at position {cycle_pos}")
            return
        
        out = self._save_frame(cropped, keyname, cycle_pos)
        crop_x, crop_y = self._crop_coords[cycle_pos]
        print(f"[ok] {keyname} (pos {cycle_pos}) -> {out} [cropped {self._crop_size}x{self._crop_size} from {crop_x},{crop_y}]")

    def on_press(self, key) -> None:
        try:
            if hasattr(key, "char") and key.char is not None:
                ch = key.char.lower()
                if ch == "q":
                    self._handle_keypress("q")
                elif ch == "e":
                    self._handle_keypress("e")
            else:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt):
                    self._handle_keypress("alt")
                elif key == keyboard.Key.esc:
                    print("[info] ESC detected; exiting.")
                    self._running = False
                    raise StopIteration
        except Exception as exc:
            print(f"[err] on_press error: {exc}")
        # Always return None
        return None

    def run(self) -> None:
        print("[info] Listening for Alt / Q / E ... (ESC to quit)")
        print("[info] Saving only positions 1-3 as 26x26 crops:")
        print(f"[info] Position 1 (Alt): crop at {self._crop_coords[1]}")
        print(f"[info] Position 2 (Q/E): crop at {self._crop_coords[2]}")
        print(f"[info] Position 3 (Q/E): crop at {self._crop_coords[3]}")
        print("[info] Position 4 will be skipped")
        
        with keyboard.Listener(on_press=self.on_press) as listener:
            while self._running:
                time.sleep(0.05)
            listener.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="MTA: San Andreas")
    ap.add_argument("--save-dir", default="screenshots")
    ap.add_argument("--delay-ms", type=int, default=0)
    ap.add_argument("--no-foreground", action="store_true")
    args = ap.parse_args()

    kc = KeypressCapture(
        title_contains=args.title,
        save_dir=args.save_dir,
        post_press_delay_ms=args.delay_ms,
        bring_foreground=(not args.no_foreground),
    )
    kc.run()

if __name__ == "__main__":
    main()
