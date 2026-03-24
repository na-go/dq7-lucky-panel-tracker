"""Screen Capture - Steam版DQ7のゲームウィンドウをキャプチャ

WGC (Windows Graphics Capture) を優先使用し、ウィンドウ単体をキャプチャする。
WGCが利用できない環境ではmssによるスクリーンキャプチャにフォールバック。
"""

from __future__ import annotations

from typing import Generator, Optional, Tuple
import time

import cv2
import mss
import numpy as np


class ScreenCapture:
    def __init__(self):
        self.region: Optional[Tuple[int, int, int, int]] = None  # (left, top, width, height)
        self.hwnd: Optional[int] = None
        self._wgc = None  # WgcCapture instance

    def set_region(self, region: Tuple[int, int, int, int]):
        """キャプチャ領域を手動設定 (left, top, width, height)"""
        self.region = region
        self.hwnd = None
        self._stop_wgc()

    def auto_detect_window(self, title: str = "DRAGON QUEST VII") -> bool:
        """ウィンドウタイトルから自動検出 → WGCキャプチャ開始"""
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
            self.hwnd = win._hWnd
            self._start_wgc()
            return True
        except Exception:
            return False

    @property
    def using_wgc(self) -> bool:
        """WGCモードで動作中かどうか"""
        return self._wgc is not None

    def grab(self) -> Optional[np.ndarray]:
        """現在のフレームを1枚取得（BGR numpy array）

        WGC利用可能ならウィンドウ単体をキャプチャ（上の重なりを無視）。
        そうでなければmssでスクリーンキャプチャ。
        """
        # WGCモード
        if self._wgc is not None:
            frame = self._wgc.grab()
            if frame is not None:
                w, h = self._wgc.size
                self.region = (0, 0, w, h)
                return frame

        # フォールバック: mss
        if self.region is None:
            return None
        self._update_region_from_hwnd()
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

    # ------ WGC管理 ------

    def _start_wgc(self):
        """WGCキャプチャを開始（失敗しても問題なし、mssフォールバック）"""
        self._stop_wgc()
        self._wgc_error: Optional[str] = None
        if self.hwnd is None:
            return
        try:
            from .wgc_capture import WgcCapture
            wgc = WgcCapture()
            if not wgc.start(self.hwnd):
                self._wgc_error = wgc.last_error or "start failed"
                wgc.stop()
                return
            if not wgc.wait_first_frame(timeout=1.0):
                self._wgc_error = "first frame timeout"
                wgc.stop()
                return
            self._wgc = wgc
        except Exception as e:
            self._wgc_error = str(e)
            self._wgc = None

    def _stop_wgc(self):
        if self._wgc is not None:
            self._wgc.stop()
            self._wgc = None

    # ------ mssフォールバック用 ------

    def _update_region_from_hwnd(self):
        """hwndからウィンドウの現在位置を再取得"""
        if self.hwnd is None:
            return
        try:
            import win32gui
            if not win32gui.IsWindow(self.hwnd):
                self.hwnd = None
                return
            rect = win32gui.GetWindowRect(self.hwnd)
            self.region = (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])
        except Exception:
            pass
