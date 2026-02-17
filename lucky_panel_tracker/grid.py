"""Grid Detector - 画像からパネルグリッドの位置を検出し、各セルを切り出す"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class GridCell:
    row: int
    col: int
    x: int  # 左上x座標
    y: int  # 左上y座標
    w: int  # 幅
    h: int  # 高さ


class GridDetector:
    def detect(self, frame: np.ndarray) -> list[list[GridCell]]:
        """フレームからグリッド構造を検出

        Returns: grid[row][col] = GridCell
        """
        h, w = frame.shape[:2]
        image_area = h * w

        # 1. グレースケール変換
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 2. 閾値処理
        _, thresh = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)

        # 3. ノイズ除去 (morphologyEx MORPH_OPEN)
        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

        # 4. パネル間のギャップを確保 (erode)
        thresh = cv2.erode(thresh, kernel, iterations=2)

        # 5. 輪郭検出
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 6. 面積フィルタ (画像サイズに基づいて動的計算)
        # 最大パネル数=24として計算し、余裕を持たせる
        min_area = image_area / 24 / 4
        max_area = image_area / 24 * 3

        cells = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(cnt)
            # 幅・高さの比率チェック（極端に細長いものを除外）
            aspect = bw / bh if bh > 0 else 0
            if aspect < 0.5 or aspect > 2.0:
                continue
            cells.append((bx, by, bw, bh))

        # 7. y座標で行グループ化 → x座標ソート
        cells.sort(key=lambda c: c[1])  # y座標でソート

        rows = []
        current_row = [cells[0]] if cells else []
        for i in range(1, len(cells)):
            # y座標の差が20px以内なら同じ行
            if abs(cells[i][1] - current_row[0][1]) < 20:
                current_row.append(cells[i])
            else:
                rows.append(current_row)
                current_row = [cells[i]]
        if current_row:
            rows.append(current_row)

        # 各行内をx座標でソート
        grid = []
        for r_idx, row in enumerate(rows):
            row.sort(key=lambda c: c[0])
            grid_row = []
            for c_idx, (bx, by, bw, bh) in enumerate(row):
                grid_row.append(GridCell(row=r_idx, col=c_idx, x=bx, y=by, w=bw, h=bh))
            grid.append(grid_row)

        return grid

    def crop_cell(self, frame: np.ndarray, cell: GridCell) -> np.ndarray:
        """指定セルの画像を切り出し"""
        return frame[cell.y:cell.y + cell.h, cell.x:cell.x + cell.w]

    def crop_cell_center(self, frame: np.ndarray, cell: GridCell, margin: float = 0.25) -> np.ndarray:
        """セル中心部分のみ切り出し（マージン除外）"""
        mx = int(cell.w * margin)
        my = int(cell.h * margin)
        return frame[cell.y + my:cell.y + cell.h - my, cell.x + mx:cell.x + cell.w - mx]

    def detect_difficulty(self, grid: list[list[GridCell]]) -> dict:
        """グリッドサイズから難易度情報を返す"""
        total = sum(len(row) for row in grid)
        difficulty_map = {
            12: {"name": "甘口", "rows": 3, "cols": 4, "swaps": 2},
            16: {"name": "中辛", "rows": 4, "cols": 4, "swaps": 3},
            20: {"name": "辛口", "rows": 4, "cols": 5, "swaps": 5},
            24: {"name": "激辛", "rows": 4, "cols": 6, "swaps": 7},
        }
        return difficulty_map.get(total, {"name": "不明", "swaps": 0})
