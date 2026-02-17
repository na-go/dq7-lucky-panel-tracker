"""Step 1 検証: グリッド検出のテスト"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
import numpy as np
from lucky_panel_tracker.grid import GridDetector


def test_grid_detection():
    # サンプル画像を読み込み
    img_path = os.path.join(os.path.dirname(__file__), '..', 'samples', 'phase1', 'full_face_up.png')
    frame = cv2.imread(img_path)
    assert frame is not None, f"画像が読み込めません: {img_path}"

    print(f"画像サイズ: {frame.shape[1]}x{frame.shape[0]}")

    detector = GridDetector()

    # グリッド検出
    grid = detector.detect(frame)

    # 検証: 4行であること
    print(f"\n検出行数: {len(grid)}")
    assert len(grid) == 4, f"4行期待だが{len(grid)}行検出"

    # 検証: 各行6列であること
    for r_idx, row in enumerate(grid):
        print(f"  Row {r_idx}: {len(row)}列")
        assert len(row) == 6, f"Row {r_idx}: 6列期待だが{len(row)}列検出"

    # 合計パネル数
    total = sum(len(row) for row in grid)
    print(f"\n合計パネル数: {total}")
    assert total == 24, f"24パネル期待だが{total}パネル検出"

    # 難易度判定
    difficulty = detector.detect_difficulty(grid)
    print(f"難易度: {difficulty['name']} (swaps={difficulty['swaps']})")
    assert difficulty["name"] == "激辛"
    assert difficulty["swaps"] == 7

    # 各セルの詳細表示
    print("\n--- 各セル詳細 ---")
    for row in grid:
        for cell in row:
            print(f"  [{cell.row},{cell.col}] x={cell.x} y={cell.y} w={cell.w} h={cell.h} area={cell.w*cell.h}")

    # デバッグ画像生成
    debug_img = frame.copy()
    for row in grid:
        for cell in row:
            cv2.rectangle(debug_img, (cell.x, cell.y), (cell.x + cell.w, cell.y + cell.h), (0, 255, 0), 2)
            cv2.putText(debug_img, f"{cell.row},{cell.col}", (cell.x + 2, cell.y + 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

    output_path = os.path.join(os.path.dirname(__file__), '..', 'samples', 'test_grid_result.png')
    cv2.imwrite(output_path, debug_img)
    print(f"\nデバッグ画像出力: {output_path}")

    print("\n=== Step 1: グリッド検出 OK ===")


if __name__ == "__main__":
    test_grid_detection()
