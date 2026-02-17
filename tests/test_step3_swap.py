"""Step 3 検証: スワップ検出のテスト（動画から）"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import cv2
from lucky_panel_tracker.grid import GridDetector
from lucky_panel_tracker.monitor import ShuffleMonitor


def test_swap_detection():
    video_path = os.path.join(os.path.dirname(__file__), '..', 'samples', 'test_video.mp4')
    assert os.path.exists(video_path), f"動画が見つかりません: {video_path}"

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"動画情報: {w}x{h}, {fps}fps, {total_frames}フレーム, {total_frames/fps:.1f}秒")

    # 最初のフレームでグリッド検出（裏面状態のはず）
    # まず全フレーム裏面画像でグリッドを検出
    # Phase1用の画像を使ってグリッド検出
    phase1_path = os.path.join(os.path.dirname(__file__), '..', 'samples', 'phase1', 'full_face_up.png')
    phase1_frame = cv2.imread(phase1_path)
    detector = GridDetector()
    grid = detector.detect(phase1_frame)
    difficulty = detector.detect_difficulty(grid)
    print(f"グリッド: {len(grid)}行, 難易度: {difficulty['name']}, 期待スワップ: {difficulty['swaps']}")

    # ShuffleMonitor設定
    expected_swaps = difficulty["swaps"]
    monitor = ShuffleMonitor(grid, expected_swaps)

    # スワップ検出結果を記録
    detected_swaps = []

    def on_swap(pos_a, pos_b, count):
        detected_swaps.append((pos_a, pos_b))
        print(f"  Swap {count}: [{pos_a[0]},{pos_a[1]}] <-> [{pos_b[0]},{pos_b[1]}]")

    completed = [False]
    def on_complete():
        completed[0] = True
        print("  >> シャッフル完了!")

    monitor.on_swap = on_swap
    monitor.on_complete = on_complete

    # フレーム処理
    print(f"\n--- フレーム処理開始 ---")
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        monitor.process_frame(frame)
        frame_count += 1

        # 状態遷移のログ
        if frame_count % 30 == 0:
            print(f"  frame {frame_count}: state={monitor.state.name}, swaps={monitor.swap_count}")

    cap.release()
    print(f"\n処理フレーム数: {frame_count}")
    print(f"検出スワップ数: {len(detected_swaps)}")
    print(f"完了フラグ: {completed[0]}")

    # 期待結果
    expected = [
        ((3, 5), (0, 5)),  # Swap1
        ((3, 1), (1, 0)),  # Swap2
        ((0, 2), (2, 2)),  # Swap3
        ((3, 0), (3, 3)),  # Swap4
        ((0, 4), (2, 3)),  # Swap5
        ((2, 1), (0, 3)),  # Swap6
        ((3, 5), (2, 1)),  # Swap7
    ]

    print(f"\n--- スワップ検出結果 vs 期待値 ---")
    all_match = True
    for i, (detected, expect) in enumerate(zip(detected_swaps, expected)):
        det_a, det_b = detected
        exp_a, exp_b = expect
        # 順序不問で比較
        match = (set([det_a, det_b]) == set([exp_a, exp_b]))
        status = "OK" if match else "NG"
        if not match:
            all_match = False
        print(f"  Swap {i+1}: detected=[{det_a[0]},{det_a[1]}]<->[{det_b[0]},{det_b[1]}]  "
              f"expected=[{exp_a[0]},{exp_a[1]}]<->[{exp_b[0]},{exp_b[1]}]  [{status}]")

    assert len(detected_swaps) == expected_swaps, \
        f"{expected_swaps}回期待だが{len(detected_swaps)}回検出"
    assert all_match, "スワップのセルペアが一致しない"

    print(f"\n=== Step 3: スワップ検出 OK ===")


if __name__ == "__main__":
    test_swap_detection()
