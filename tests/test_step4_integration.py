"""Step 4 検証: 結合テスト（Phase1初期配置 → Phase2スワップ → 最終配置）"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
from lucky_panel_tracker.grid import GridDetector
from lucky_panel_tracker.classifier import ItemClassifier
from lucky_panel_tracker.tracker import PanelState
from lucky_panel_tracker.monitor import ShuffleMonitor


def test_integration():
    base = os.path.join(os.path.dirname(__file__), '..')

    # === Phase 1: 初期配置記録 ===
    print("=== Phase 1: 初期配置記録 ===")
    phase1_path = os.path.join(base, 'samples', 'phase1', 'full_face_up.png')
    frame = cv2.imread(phase1_path)
    assert frame is not None

    detector = GridDetector()
    grid = detector.detect(frame)
    difficulty = detector.detect_difficulty(grid)
    print(f"難易度: {difficulty['name']} ({difficulty['rows']}x{difficulty['cols']}), 期待スワップ: {difficulty['swaps']}")

    classifier = ItemClassifier()
    mapping = classifier.register_from_grid(frame, grid)

    rows = difficulty["rows"]
    cols = difficulty["cols"]
    state = PanelState(rows, cols)
    for (r, c), item_id in mapping.items():
        state.set_initial(r, c, item_id)

    print("\n初期配置:")
    state.print_grid()

    # === Phase 2: シャッフル追跡 ===
    print("\n=== Phase 2: シャッフル追跡 ===")
    video_path = os.path.join(base, 'samples', 'test_video.mp4')
    cap = cv2.VideoCapture(video_path)

    monitor = ShuffleMonitor(grid, difficulty["swaps"])

    swap_log = []
    def on_swap(pos_a, pos_b, count):
        state.apply_swap(pos_a, pos_b)
        swap_log.append((pos_a, pos_b))
        print(f"  Swap {count}: [{pos_a[0]},{pos_a[1]}] <-> [{pos_b[0]},{pos_b[1]}]")

    completed = [False]
    def on_complete():
        completed[0] = True

    monitor.on_swap = on_swap
    monitor.on_complete = on_complete

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        monitor.process_frame(frame)

    cap.release()

    assert completed[0], "シャッフルが完了しなかった"
    assert len(swap_log) == difficulty["swaps"], \
        f"スワップ回数が一致しない: {len(swap_log)} != {difficulty['swaps']}"

    # === 最終配置表示 ===
    print(f"\n=== 最終配置（{len(swap_log)}回スワップ後） ===")
    state.print_grid()

    # === 検証: 手動でスワップを適用した結果と一致するか ===
    print("\n=== 検証: 手動スワップ適用 ===")
    expected_swaps = [
        ((3, 5), (0, 5)),
        ((3, 1), (1, 0)),
        ((0, 2), (2, 2)),
        ((3, 0), (3, 3)),
        ((0, 4), (2, 3)),
        ((2, 1), (0, 3)),
        ((3, 5), (2, 1)),
    ]

    verify_state = PanelState(rows, cols)
    for (r, c), item_id in mapping.items():
        verify_state.set_initial(r, c, item_id)

    for pos_a, pos_b in expected_swaps:
        verify_state.apply_swap(pos_a, pos_b)

    print("期待最終配置:")
    verify_state.print_grid()

    # グリッド一致確認
    match = True
    for r in range(rows):
        for c in range(cols):
            if state.grid[r][c] != verify_state.grid[r][c]:
                print(f"  不一致: [{r},{c}] actual={state.grid[r][c]} expected={verify_state.grid[r][c]}")
                match = False

    assert match, "最終配置が期待値と一致しない"

    # === ペア情報の表示 ===
    print("\n=== 最終配置のペア位置 ===")
    item_positions = {}
    for r in range(rows):
        for c in range(cols):
            item = state.grid[r][c]
            if item not in item_positions:
                item_positions[item] = []
            item_positions[item].append((r, c))

    for item_id, positions in sorted(item_positions.items()):
        pos_str = ", ".join(f"[{r},{c}]" for r, c in positions)
        label = "ペア" if len(positions) == 2 else "特殊"
        print(f"  {item_id}: {pos_str} [{label}]")

    print("\n=== Step 4: 結合テスト OK ===")


if __name__ == "__main__":
    test_integration()
