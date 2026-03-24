"""Shuffle Monitor - Phase2のフレーム列からスワップイベントを検出"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional

import cv2
import numpy as np

from .grid import GridCell, GridDetector


class ShuffleMonitor:
    """連続フレームを受け取り、スワップイベントを検出する

    パフォーマンス最適化:
    - フルフレームではなくボード領域のROIだけで差分計算
    - グレースケール変換して比較（チャンネル数1/3）
    - frame.copy()を最小化（ROIのみ保持）
    """

    STABLE_THRESHOLD = 1.5      # 全体差分の安定判定閾値
    CELL_DIFF_MARGIN = 0.25     # セル差分計算時の端カットマージン
    STABLE_COUNT_NEEDED = 3     # 安定判定に必要な連続安定フレーム数

    class State(Enum):
        WAITING_FLIP = auto()   # 全パネル裏返し待ち
        IDLE = auto()           # スワップ間の静止
        SWAPPING = auto()       # スワップアニメーション中
        DONE = auto()           # シャッフル完了

    def __init__(self, grid: list[list[GridCell]], expected_swaps: int):
        self.grid = grid
        self.expected_swaps = expected_swaps
        self.state = self.State.WAITING_FLIP
        self.swap_count = 0
        self.stable_count = 0
        self.swap_detected_this_event = False
        self.on_swap: Optional[Callable] = None
        self.on_complete: Optional[Callable] = None
        self._detector = GridDetector()

        # ボード領域のバウンディングボックス（ROI）を事前計算
        self._board_roi = self._calc_board_roi()

        # フレーム参照（グレースケールROIのみ保持）
        self._stable_gray: Optional[np.ndarray] = None
        self._prev_gray: Optional[np.ndarray] = None
        # stable_frame はセル差分計算用にBGRで保持
        self.stable_frame: Optional[np.ndarray] = None

    def _calc_board_roi(self) -> tuple[int, int, int, int]:
        """グリッド全体のバウンディングボックスを計算 (y1, y2, x1, x2)"""
        min_x = min(cell.x for row in self.grid for cell in row)
        min_y = min(cell.y for row in self.grid for cell in row)
        max_x = max(cell.x + cell.w for row in self.grid for cell in row)
        max_y = max(cell.y + cell.h for row in self.grid for cell in row)
        return (min_y, max_y, min_x, max_x)

    def _to_board_gray(self, frame: np.ndarray) -> np.ndarray:
        """フレームからボード領域を切り出してグレースケール変換"""
        y1, y2, x1, x2 = self._board_roi
        roi = frame[y1:y2, x1:x2]
        return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    def _calc_overall_diff(self, gray_a: np.ndarray, gray_b: np.ndarray) -> float:
        """2つのグレースケールROI間の平均差分"""
        diff = cv2.absdiff(gray_a, gray_b)
        return float(np.mean(diff))

    def _calc_cell_diffs(self, frame: np.ndarray) -> list[tuple[float, int, int]]:
        """各セル中心部の差分を計算し、(diff, row, col)のリストを返す"""
        diffs = []
        for row in self.grid:
            for cell in row:
                center_cur = self._detector.crop_cell_center(
                    frame, cell, self.CELL_DIFF_MARGIN)
                center_ref = self._detector.crop_cell_center(
                    self.stable_frame, cell, self.CELL_DIFF_MARGIN)
                diff = float(np.mean(cv2.absdiff(center_cur, center_ref)))
                diffs.append((diff, cell.row, cell.col))
        return diffs

    def process_frame(self, frame: np.ndarray):
        """1フレーム処理"""
        if self.state == self.State.DONE:
            return

        if self.state == self.State.WAITING_FLIP:
            self._handle_waiting_flip(frame)
        elif self.state == self.State.IDLE:
            self._handle_idle(frame)
        elif self.state == self.State.SWAPPING:
            self._handle_swapping(frame)

    def _handle_waiting_flip(self, frame: np.ndarray):
        """裏返し完了を待つ。
        直前フレームとの差分で安定判定。大きな変化を検出した後、安定に戻ったらIDLEへ。
        """
        gray = self._to_board_gray(frame)

        if self._prev_gray is None:
            self._prev_gray = gray.copy()
            self._stable_gray = gray.copy()
            self.stable_frame = frame.copy()
            return

        frame_diff = self._calc_overall_diff(gray, self._prev_gray)
        self._prev_gray = gray  # グレーROIは小さいのでコピー不要（次フレームで上書き前に使用完了）

        if frame_diff >= self.STABLE_THRESHOLD:
            # 変化中（裏返しアニメーション）
            self._flip_detected = True
            self.stable_count = 0
        else:
            if getattr(self, '_flip_detected', False):
                self.stable_count += 1
                if self.stable_count >= self.STABLE_COUNT_NEEDED:
                    # 裏返し完了 → IDLE遷移
                    self.state = self.State.IDLE
                    self._stable_gray = gray.copy()
                    self.stable_frame = frame.copy()
                    self.stable_count = 0

    def _handle_idle(self, frame: np.ndarray):
        """スワップ間の安定状態"""
        gray = self._to_board_gray(frame)
        overall_diff = self._calc_overall_diff(gray, self._stable_gray)

        if overall_diff >= self.STABLE_THRESHOLD:
            # スワップ開始検出
            self.state = self.State.SWAPPING
            self.swap_detected_this_event = False
            self._prev_gray = gray.copy()
            # スワップ位置を検出
            self._detect_swap(frame)
        # IDLE安定時: stable_frameは毎フレーム更新しない（変化がないため不要）

    def _handle_swapping(self, frame: np.ndarray):
        """スワップアニメーション中
        直前フレームとの差分で安定復帰を判定する。
        """
        gray = self._to_board_gray(frame)

        if self._prev_gray is None:
            self._prev_gray = gray.copy()
            return

        frame_diff = self._calc_overall_diff(gray, self._prev_gray)
        self._prev_gray = gray  # 次フレームで参照

        if frame_diff < self.STABLE_THRESHOLD:
            self.stable_count += 1
            if self.stable_count >= self.STABLE_COUNT_NEEDED:
                # 安定に戻った → スワップ完了
                self.state = self.State.IDLE
                self._stable_gray = gray.copy()
                self.stable_frame = frame.copy()
                self.stable_count = 0
                self._prev_gray = None

                # 期待スワップ回数に達したか確認
                if self.swap_count >= self.expected_swaps:
                    self.state = self.State.DONE
                    if self.on_complete:
                        self.on_complete()
        else:
            self.stable_count = 0

    def _detect_swap(self, frame: np.ndarray):
        """スワップ開始フレームからtop2セルを検出"""
        if self.swap_detected_this_event:
            return

        diffs = self._calc_cell_diffs(frame)
        diffs.sort(reverse=True)

        if len(diffs) >= 2:
            top1_diff, r1, c1 = diffs[0]
            top2_diff, r2, c2 = diffs[1]

            self.swap_detected_this_event = True
            self.swap_count += 1

            if self.on_swap:
                self.on_swap((r1, c1), (r2, c2), self.swap_count)
