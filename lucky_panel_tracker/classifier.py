"""Item Classifier - パネル画像からアイテムを識別（テンプレートマッチング）"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .grid import GridCell, GridDetector


@dataclass
class ItemTemplate:
    item_id: str           # 内部ID ("item_00", "item_01", ...)
    thumbnail: np.ndarray  # サムネイル画像（GUI表示用）
    template: np.ndarray   # テンプレート画像（マッチング用）
    positions: list = field(default_factory=list)  # 登録時の(row, col)リスト


class ItemClassifier:
    MATCH_THRESHOLD = 0.85  # 同一アイテム判定の閾値
    TEMPLATE_SIZE = (48, 48)  # テンプレートを統一サイズにリサイズ

    def __init__(self):
        self.templates: list[ItemTemplate] = []
        self._next_id = 0

    def _new_id(self) -> str:
        item_id = f"item_{self._next_id:02d}"
        self._next_id += 1
        return item_id

    def _match_best(self, cell_img: np.ndarray) -> tuple[int, float]:
        """既存テンプレートと比較し、最も一致するインデックスとスコアを返す。
        テンプレートが空なら (-1, 0.0) を返す。
        """
        if not self.templates:
            return -1, 0.0

        resized = cv2.resize(cell_img, self.TEMPLATE_SIZE)
        best_idx = -1
        best_score = 0.0

        for i, tmpl in enumerate(self.templates):
            result = cv2.matchTemplate(resized, tmpl.template, cv2.TM_CCOEFF_NORMED)
            score = result[0][0]  # テンプレートと同サイズなので1点のみ
            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx, best_score

    def register_from_grid(self, frame: np.ndarray, grid: list[list[GridCell]]) -> dict:
        """Phase1のフレームから全アイテムを自動登録

        Returns: {(row, col): item_id} のマッピング
        """
        self.templates.clear()
        self._next_id = 0
        detector = GridDetector()
        mapping = {}

        for row in grid:
            for cell in row:
                cell_img = detector.crop_cell(frame, cell)
                best_idx, best_score = self._match_best(cell_img)

                if best_idx >= 0 and best_score > self.MATCH_THRESHOLD:
                    # 既存テンプレートに一致
                    item_id = self.templates[best_idx].item_id
                    self.templates[best_idx].positions.append((cell.row, cell.col))
                else:
                    # 新規アイテムとして登録
                    item_id = self._new_id()
                    resized = cv2.resize(cell_img, self.TEMPLATE_SIZE)
                    tmpl = ItemTemplate(
                        item_id=item_id,
                        thumbnail=cell_img.copy(),
                        template=resized,
                        positions=[(cell.row, cell.col)],
                    )
                    self.templates.append(tmpl)

                mapping[(cell.row, cell.col)] = item_id

        return mapping

    def classify(self, cell_image: np.ndarray) -> tuple[str, float]:
        """セル画像からアイテムを識別
        Returns: (item_id, confidence)
        """
        best_idx, best_score = self._match_best(cell_image)
        if best_idx >= 0:
            return self.templates[best_idx].item_id, best_score
        return "unknown", 0.0
