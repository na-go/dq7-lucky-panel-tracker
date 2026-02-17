"""Shuffle Monitor - Phase2のフレーム列からスワップイベントを検出"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Optional

import cv2
import numpy as np

from .grid import GridCell, GridDetector


class ShuffleMonitor:
    """連続フレームを受け取り、スワップイベントを検出する"""

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
        self.stable_frame: Optional[np.ndarray] = None
        self.prev_frame: Optional[np.ndarray] = None  # 直前フレーム（安定復帰判定用）
        self.swap_count = 0
        self.stable_count = 0
        self.swap_detected_this_event = False
        self.on_swap: Optional[Callable] = None
        self.on_complete: Optional[Callable] = None
        self._detector = GridDetector()

    def _calc_overall_diff(self, frame_a: np.ndarray, frame_b: np.ndarray) -> float:
        """2フレーム間の全体平均差分"""
        diff = cv2.absdiff(frame_a, frame_b)
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
        if self.prev_frame is None:
            self.prev_frame = frame.copy()
            self.stable_frame = frame.copy()
            return

        frame_diff = self._calc_overall_diff(frame, self.prev_frame)
        self.prev_frame = frame.copy()

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
                    self.stable_frame = frame.copy()
                    self.stable_count = 0

    def _handle_idle(self, frame: np.ndarray):
        """スワップ間の安定状態"""
        overall_diff = self._calc_overall_diff(frame, self.stable_frame)

        if overall_diff >= self.STABLE_THRESHOLD:
            # スワップ開始検出
            self.state = self.State.SWAPPING
            self.swap_detected_this_event = False
            # 最初のフレームでtop2を取る
            self._detect_swap(frame)
        else:
            # 安定継続 → 安定フレームを更新
            self.stable_frame = frame.copy()

    def _handle_swapping(self, frame: np.ndarray):
        """スワップアニメーション中
        直前フレームとの差分で安定復帰を判定する。
        スワップ後はパネルが入れ替わるため、stable_frameとの差分は残り続ける。
        """
        if self.prev_frame is None:
            self.prev_frame = frame.copy()
            return

        frame_diff = self._calc_overall_diff(frame, self.prev_frame)
        self.prev_frame = frame.copy()

        if frame_diff < self.STABLE_THRESHOLD:
            self.stable_count += 1
            if self.stable_count >= self.STABLE_COUNT_NEEDED:
                # 安定に戻った → スワップ完了
                self.state = self.State.IDLE
                self.stable_frame = frame.copy()
                self.stable_count = 0

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
