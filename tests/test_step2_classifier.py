"""Step 2 検証: アイテム分類のテスト"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
from lucky_panel_tracker.grid import GridDetector
from lucky_panel_tracker.classifier import ItemClassifier


def test_item_classification():
    img_path = os.path.join(os.path.dirname(__file__), '..', 'samples', 'phase1', 'full_face_up.png')
    frame = cv2.imread(img_path)
    assert frame is not None

    # グリッド検出
    detector = GridDetector()
    grid = detector.detect(frame)

    # アイテム分類
    classifier = ItemClassifier()
    mapping = classifier.register_from_grid(frame, grid)

    print(f"テンプレート数: {len(classifier.templates)}")

    # 各テンプレートの詳細
    print("\n--- テンプレート詳細 ---")
    pairs = 0
    singles = 0
    for tmpl in classifier.templates:
        count = len(tmpl.positions)
        if count == 2:
            pairs += 1
        elif count == 1:
            singles += 1
        label = "ペア" if count == 2 else "特殊" if count == 1 else f"異常({count}枚)"
        print(f"  {tmpl.item_id}: {count}枚 {tmpl.positions} [{label}]")

    # 検証: ペア + 特殊パネルで24枚になること
    total_panels = sum(len(t.positions) for t in classifier.templates)
    print(f"\nペア: {pairs}種, 特殊(1枚): {singles}種, 合計パネル数: {total_panels}")
    assert total_panels == 24, f"合計24パネル期待だが{total_panels}"

    # 検証: 3枚以上のグループがないこと
    for tmpl in classifier.templates:
        assert len(tmpl.positions) <= 2, f"{tmpl.item_id}が{len(tmpl.positions)}枚ある（最大2枚）"

    # 検証: ペア数が妥当（最低10ペア以上）
    assert pairs >= 10, f"ペアが{pairs}種しかない（最低10種期待）"

    # マッピング表示
    print("\n--- パネル配置 ---")
    for r in range(len(grid)):
        row_str = ""
        for c in range(len(grid[r])):
            item_id = mapping.get((r, c), "???")
            row_str += f" {item_id:>8}"
        print(f"  Row {r}:{row_str}")

    # 全セルがマッピングされていることを検証
    assert len(mapping) == 24, f"24セル期待だが{len(mapping)}セルがマッピング"

    # confidenceテスト: ペアアイテムの2枚が互いに高スコアであること
    print("\n--- ペア内相互スコア ---")
    min_pair_conf = 1.0
    for tmpl in classifier.templates:
        if len(tmpl.positions) == 2:
            pos_a, pos_b = tmpl.positions
            # pos_bのcrop画像でclassify
            cell_b = None
            for row in grid:
                for cell in row:
                    if cell.row == pos_b[0] and cell.col == pos_b[1]:
                        cell_b = cell
                        break
            if cell_b:
                crop_b = detector.crop_cell(frame, cell_b)
                classified_id, conf = classifier.classify(crop_b)
                if conf < min_pair_conf:
                    min_pair_conf = conf
                match = "OK" if classified_id == tmpl.item_id else "NG"
                print(f"  {tmpl.item_id}: [{pos_b[0]},{pos_b[1]}] -> {classified_id} conf={conf:.3f} [{match}]")

    print(f"\n  ペア内最低confidence: {min_pair_conf:.3f}")
    assert min_pair_conf > 0.85, f"ペア内confidence閾値0.85を下回る (min={min_pair_conf:.3f})"

    print("\n=== Step 2: アイテム分類 OK ===")


if __name__ == "__main__":
    test_item_classification()
