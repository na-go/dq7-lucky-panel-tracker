"""Screen Capture - Steam版DQ7のゲームウィンドウをキャプチャ"""

from __future__ import annotations

from typing import Generator, Optional, Tuple
import time

import cv2
import mss
import numpy as np


class ScreenCapture:
    def __init__(self):
        self.region: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)

    def set_region(self, region: Tuple[int, int, int, int]):
        """キャプチャ領域を手動設定 (left, top, width, height)"""
        self.region = region

    def auto_detect_window(self, title: str = "DRAGON QUEST VII") -> bool:
        """ウィンドウタイトルから自動検出 (pygetwindow)"""
        try:
            import pygetwindow as gw
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return False
            win = windows[0]
            if win.isMinimized:
                win.restore()
                time.sleep(0.3)
            self.region = (win.left, win.top, win.width, win.height)
            return True
        except Exception:
            return False

    def grab(self) -> Optional[np.ndarray]:
        """現在のフレームを1枚取得（BGR numpy array）
        mssはスレッドローカルなので毎回新しいインスタンスを使う。
        """
        if self.region is None:
            return None
        left, top, width, height = self.region
        monitor = {"left": left, "top": top, "width": width, "height": height}
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame

    def grab_continuous(self, fps: int = 30) -> Generator[np.ndarray, None, None]:
        """連続キャプチャ（Phase2用、ジェネレータ）"""
        interval = 1.0 / fps
        while True:
            start = time.perf_counter()
            frame = self.grab()
            if frame is not None:
                yield frame
            elapsed = time.perf_counter() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
