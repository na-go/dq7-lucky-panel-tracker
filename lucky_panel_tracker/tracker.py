"""State Tracker - パネル配置の状態管理"""

from __future__ import annotations

from typing import List, Optional, Tuple


class PanelState:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.grid: List[List[Optional[str]]] = [[None] * cols for _ in range(rows)]
        self.swap_log: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

    def set_initial(self, row: int, col: int, item_id: str):
        """Phase1: 初期配置を記録"""
        self.grid[row][col] = item_id

    def apply_swap(self, pos_a: tuple[int, int], pos_b: tuple[int, int]):
        """Phase2: スワップを適用"""
        ra, ca = pos_a
        rb, cb = pos_b
        self.grid[ra][ca], self.grid[rb][cb] = self.grid[rb][cb], self.grid[ra][ca]
        self.swap_log.append((pos_a, pos_b))

    def get_result(self) -> List[List[Optional[str]]]:
        """最終配置を返す"""
        return self.grid

    def print_grid(self):
        """デバッグ用: グリッドを表示"""
        for r in range(self.rows):
            row_str = ""
            for c in range(self.cols):
                val = self.grid[r][c] or "----"
                row_str += f" {val:>8}"
            print(f"  Row {r}:{row_str}")
