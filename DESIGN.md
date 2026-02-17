# Lucky Panel Tracker 設計書

## 1. 概要

DQ7リメイク（Steam版）のラッキーパネルにおいて、シャッフル前のパネル配置を記録し、シャッフル中の入れ替えをリアルタイム追跡して、最終的なパネル配置を表示するGUIツール。

### ゴール
- シャッフル後に「どこに何があるか」が全てわかる状態を作る
- プレイヤーは表示を見ながら確実にペアを揃えられる

### 非ゴール
- ゲーム操作の自動化（カーソル移動・パネル選択）
- メモリ読み取り等のチート的アプローチ

---

## 2. ゲーム仕様

### 2.1 ラッキーパネルの流れ

```
[1] パネル全表示（表向き・静止）← ここでスクショ可能、時間制限なし
         ↓ Aボタン押下
[2] 全パネル一斉裏返し（〜0.5秒）
         ↓
[3] シャッフルアニメーション（〜6秒）
         ↓
[4] プレイ開始（カーソル出現）
```

### 2.2 グリッド構成

| 難易度 | グリッド | パネル数 | ペア数 | スワップ回数 |
|--------|---------|---------|--------|-------------|
| 甘口   | 3×4     | 12      | 6      | 2           |
| 中辛   | 4×4     | 16      | 8      | 3           |
| 辛口   | 4×5     | 20      | 10     | 5           |
| 激辛   | 4×6     | 24      | 12     | 7           |

### 2.3 シャッフルアニメーション仕様

- **スワップ回数**: 難易度により異なる（甘口2回 / 中辛3回 / 辛口5回 / 激辛7回）
- **全体所要時間**: 約6秒（激辛の場合）
- **1スワップの構造**:
  1. 2枚のパネルがグリッドから浮き上がる（グリッド上に空きが生じる）
  2. パネルは **表向き（アイテム絵柄が見える状態）** で移動
  3. 互いの位置へスライド
  4. 着地後、裏返る
  5. 次のスワップまで約0.3〜0.5秒の静止

- **1スワップの所要時間**: 約0.6秒（15フレーム @24fps）
- **スワップ間インターバル**: 約0.3〜0.5秒

---

## 3. 画像処理パラメータ（実測値）

以下は640×360解像度の動画フレームから実測した値。実際のSteam版ではウィンドウサイズが異なるため、比率ベースで正規化するか、Phase1のグリッド検出時に動的算出すること。

### 3.1 色空間パラメータ（HSV）

| 領域 | H（色相） | S（彩度） | V（明度） | 用途 |
|------|-----------|-----------|-----------|------|
| パネル表面（白〜ベージュ） | 0-180 (様々) | 0-60 | 170-255 | Phase1パネル領域検出 |
| パネル裏面（青） | 85-125 | 30-255 | 100-250 | Phase2裏面パネル判定 |
| 木目背景（茶色） | 5-25 | 50-200 | 40-100 | 背景識別 |

### 3.2 グリッド検出パラメータ

**検出方式**: グレースケール閾値 + morphology + 輪郭検出

```
手順:
1. グレースケール変換
2. 閾値処理: threshold = 130, THRESH_BINARY
3. morphologyEx(MORPH_OPEN, kernel=3x3, iterations=1)  # ノイズ除去
4. erode(kernel=3x3, iterations=2)  # パネル間のギャップを確保
5. findContours(RETR_EXTERNAL)
6. フィルタ: 面積 1500-8000, 幅 30-100px, 高さ 30-100px
7. (row, col)でソート: y座標で行グループ化(閾値20px) → x座標ソート
```

**640×360画像での実測値（激辛 4×6）**:

| パラメータ | 値 |
|-----------|-----|
| パネル領域全体 | x=115~525, y=16~255 |
| セル幅 | 57~66px (平均61.4) |
| セル高 | 50~60px (平均54.8) |
| 水平間隔 | 3~6px |
| 垂直間隔 | 5~6px |
| セル面積 | 2674~3546px² |

**注意: パネルサイズは行によって異なる**（透視変換の影響）:
- Row 0（奥）: 約59×50px
- Row 3（手前）: 約65×60px

### 3.3 スワップ検出パラメータ

**検出方式**: 直前安定フレームとの差分 + top2選択

```
アルゴリズム:
1. 全パネル裏返し完了後の最初の安定フレームを「基準フレーム」とする
2. 毎フレーム、基準フレームとの全体差分を計算
3. 全体差分が閾値(1.5)未満 → 安定状態 → 基準フレームを更新
4. 全体差分が閾値以上 → スワップ開始
5. スワップ開始の最初のフレームで、各セルのdiffを計算
6. diff上位2セルがスワップ対象
7. 安定状態に戻ったらスワップ完了 → state更新
```

**差分計算の方法**:
- 各セルの中心50%領域（上下左右25%マージンをカット）
- `mean(abs(frame_a - frame_b))` でピクセル平均差分
- 閾値: diff > 15 で「変化あり」

**実測の検出精度（激辛, 7スワップ）**:

| Swap# | 交換セル | frame+0のtop2差分 | 3位との差 |
|-------|---------|------------------|----------|
| 1 | [3,5]↔[0,5] | 73, 45 | 23 |
| 2 | [3,1]↔[1,0] | 61, 25 | 14 |
| 3 | [0,2]↔[2,2] | 40, 38 | 28 |
| 4 | [3,0]↔[3,3] | 36, 27 | 27 |
| 5 | [0,4]↔[2,3] | 38, 18 | 18 |
| 6 | [2,1]↔[0,3] | 59, 47 | 38 |
| 7 | [3,5]↔[2,1] | 65, 57 | 15 |

→ 全7スワップをframe+0のtop2で正確に検出可能。2位-3位ギャップは最低14。

**重要な注意**:
- frame+0（スワップ開始直後のフレーム）での判定が最も正確
- frame+1以降では浮遊パネルが他セルに重なりノイズが増える
- 30fpsキャプチャなら、0.3秒の安定期間中に9フレーム取得可能 → 安定判定に十分

### 3.4 アイテム分類パラメータ

**検出方式**: テンプレートマッチング (cv2.matchTemplate, TM_CCOEFF_NORMED)

- Phase1で各セルをcropして自動でテンプレート登録
- 同じアイテムは2枚あるので、12種のテンプレートに集約
- 重複判定の閾値: 正規化相関 > 0.85 → 同一アイテム
- アイテム名は不要（サムネイル画像での表示で十分）

### 3.5 フェーズ遷移検出

**全パネル裏返しの検出**:
- Phase1完了後、フレーム全体の差分を監視
- 急激な変化（全体diff > 10）が発生 → 裏返しアニメーション開始
- 差分が安定（< 1.5）に戻る → 裏返し完了 → Phase2自動開始

**シャッフル完了の検出**:
- 検出パネル数から期待スワップ回数を決定（12→2, 16→3, 20→5, 24→7）
- 期待回数に達したら完了
- フォールバック: 最後のスワップ後1秒間安定なら完了

---

## 4. システム構成

```
┌─────────────────────────────────────────────────┐
│                    GUI (tkinter)                 │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │ キャプチャ   │  │    パネル配置ビュー       │  │
│  │ プレビュー   │  │  (グリッド + サムネイル)  │  │
│  └─────────────┘  └──────────────────────────┘  │
│  [Phase1] [Phase2開始] [Phase2停止] [リセット]    │
│  ステータスバー                                   │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│              Core Engine (Python)                │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Screen   │ │ Grid     │ │ Item             │ │
│  │ Capture  │ │ Detector │ │ Classifier       │ │
│  │          │ │          │ │ (テンプレート     │ │
│  │ (mss)   │ │ (OpenCV) │ │  マッチング)      │ │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘ │
│       │            │               │             │
│  ┌────┴────────────┴───────────────┴──────────┐  │
│  │           State Tracker                    │  │
│  │  phase1: {(row,col): item_id}             │  │
│  │  phase2: swap操作の適用                     │  │
│  │  result: 最終配置 {(row,col): item_id}    │  │
│  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────┘
```

---

## 5. モジュール設計

### 5.1 Screen Capture (`capture.py`)

**責務**: Steam版DQ7のゲームウィンドウをキャプチャ

| 項目 | 内容 |
|------|------|
| ライブラリ | `mss`（高速スクリーンキャプチャ） |
| キャプチャ対象 | ゲームウィンドウ領域 |
| 出力 | numpy array (BGR) |

```python
class ScreenCapture:
    def __init__(self):
        self.region = None  # (left, top, width, height)

    def set_region(self, region: tuple[int,int,int,int]):
        """キャプチャ領域を手動設定"""

    def auto_detect_window(self, title: str = "DRAGON QUEST VII") -> bool:
        """ウィンドウタイトルから自動検出 (pygetwindow)"""

    def grab(self) -> np.ndarray:
        """現在のフレームを1枚取得（BGR numpy array）"""

    def grab_continuous(self, fps: int = 30) -> Generator[np.ndarray]:
        """連続キャプチャ（Phase2用、ジェネレータ）"""
```

### 5.2 Grid Detector (`grid.py`)

**責務**: 画像からパネルグリッドの位置を検出し、各セルを切り出す

```python
@dataclass
class GridCell:
    row: int
    col: int
    x: int      # 左上x座標
    y: int      # 左上y座標
    w: int      # 幅
    h: int      # 高さ

class GridDetector:
    def detect(self, frame: np.ndarray) -> list[list[GridCell]]:
        """フレームからグリッド構造を検出

        手順:
        1. gray = cvtColor(frame, BGR2GRAY)
        2. _, thresh = threshold(gray, 130, THRESH_BINARY)
        3. morphologyEx(thresh, MORPH_OPEN, 3x3, iter=1)
        4. erode(thresh, 3x3, iter=2)
        5. findContours(RETR_EXTERNAL)
        6. 面積フィルタ: 画像面積/パネル数/4 < area < 画像面積/パネル数*3
           ※ 閾値はハードコードせず画像サイズに基づいて動的計算
        7. y座標で行グループ化 → x座標ソート
        
        Returns: grid[row][col] = GridCell
        """

    def crop_cell(self, frame: np.ndarray, cell: GridCell) -> np.ndarray:
        """指定セルの画像を切り出し"""
        return frame[cell.y:cell.y+cell.h, cell.x:cell.x+cell.w]

    def crop_cell_center(self, frame: np.ndarray, cell: GridCell, margin: float = 0.25) -> np.ndarray:
        """セル中心部分のみ切り出し（マージン除外）
        空きセル検出で使用。端のピクセルは隣接パネルの影響を受けるため除外。
        """
        mx = int(cell.w * margin)
        my = int(cell.h * margin)
        return frame[cell.y+my:cell.y+cell.h-my, cell.x+mx:cell.x+cell.w-mx]

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
```

### 5.3 Item Classifier (`classifier.py`)

**責務**: パネル画像からアイテムを識別

```python
@dataclass
class ItemTemplate:
    item_id: str          # 内部ID ("item_00", "item_01", ...)
    thumbnail: np.ndarray # サムネイル画像（GUI表示用）
    template: np.ndarray  # テンプレート画像（マッチング用）

class ItemClassifier:
    MATCH_THRESHOLD = 0.85  # 同一アイテム判定の閾値

    def register_from_grid(self, frame: np.ndarray, grid: list[list[GridCell]]):
        """Phase1のフレームから全アイテムを自動登録

        手順:
        1. 各セルをcrop
        2. 既存テンプレートとmatchTemplate(TM_CCOEFF_NORMED)で比較
        3. 最大一致度 > MATCH_THRESHOLD → 既存アイテムに割当
        4. どれにも一致しない → 新規アイテムとして登録
        5. 結果: N種のテンプレート（各2枚のはず）
        """

    def classify(self, cell_image: np.ndarray) -> tuple[str, float]:
        """セル画像からアイテムを識別
        Returns: (item_id, confidence)
        """
```

### 5.4 State Tracker (`tracker.py`)

**責務**: パネル配置の状態管理

```python
class PanelState:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.grid: list[list[str | None]] = [[None]*cols for _ in range(rows)]
        self.swap_log: list[tuple[tuple[int,int], tuple[int,int]]] = []

    def set_initial(self, row: int, col: int, item_id: str):
        """Phase1: 初期配置を記録"""

    def apply_swap(self, pos_a: tuple[int,int], pos_b: tuple[int,int]):
        """Phase2: スワップを適用"""
        ra, ca = pos_a
        rb, cb = pos_b
        self.grid[ra][ca], self.grid[rb][cb] = self.grid[rb][cb], self.grid[ra][ca]
        self.swap_log.append((pos_a, pos_b))

    def get_result(self) -> list[list[str]]:
        """最終配置を返す"""
        return self.grid
```

### 5.5 Shuffle Monitor (`monitor.py`)

**責務**: Phase2のフレーム列からスワップイベントを検出

```python
class ShuffleMonitor:
    """連続フレームを受け取り、スワップイベントを検出する

    検出アルゴリズム（実測検証済み）:
    1. 直前の安定フレームを保持
    2. 毎フレーム、安定フレームとの全体平均差分を計算
    3. 差分 < STABLE_THRESHOLD → 安定状態 → 安定フレームを更新
    4. 差分 >= STABLE_THRESHOLD → スワップ発生
    5. スワップ開始の最初のフレームで、各セル中心部の差分を計算
    6. diff top2のセル = 交換対象
    7. on_swap(cell_a, cell_b) コールバック発火
    8. 安定状態に戻るまで待機 → 次のスワップへ

    重要: top2判定はスワップ開始直後の1フレーム目で行うこと。
    フレームが進むと浮遊パネルが他セルに重なりノイズが増える。
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
        self.stable_frame: np.ndarray | None = None
        self.swap_count = 0
        self.stable_count = 0
        self.swap_detected_this_event = False
        self.on_swap: Callable | None = None       # コールバック
        self.on_complete: Callable | None = None    # 完了コールバック

    def process_frame(self, frame: np.ndarray):
        """1フレーム処理"""
```

### 5.6 GUI (`app.py`)

**責務**: ユーザーインターフェース（tkinter）

```
┌──────────────────────────────────────────────────────────┐
│  Lucky Panel Tracker                              [×]    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──── キャプチャプレビュー ────┐  ┌── パネル配置図 ──┐  │
│  │                              │  │ [img] [img] [img] │  │
│  │  [ゲーム画面の縮小表示]      │  │ [img] [img] [img] │  │
│  │                              │  │ [img] [img] [img] │  │
│  │                              │  │ [img] [img] [img] │  │
│  └──────────────────────────────┘  └──────────────────┘  │
│                                                          │
│  ステータス: Phase2追跡中 - スワップ 5/7 検出             │
│                                                          │
│  [領域設定] [Phase1: 初期配置記録] [Phase2: シャッフル追跡] │
└──────────────────────────────────────────────────────────┘
```

**操作フロー**:

```
1. [領域設定] → ゲームウィンドウの位置を設定
2. ゲーム内で全パネルが表向きの状態にする
3. [Phase1] ボタン押下
   → 画面キャプチャ → グリッド検出 → アイテム分類 → 初期配置記録
   → パネル配置図にサムネイルが表示される
4. ゲーム内でAボタンを押してシャッフル開始
5. [Phase2] ボタン押下（またはPhase1後に自動で裏返し検出→自動開始）
   → 連続キャプチャ → スワップ検出 → リアルタイム配置更新
   → 期待スワップ回数に達したら自動停止
6. パネル配置図を見ながらプレイ
```

**パネル配置図**:
- 各セルにPhase1で切り出したサムネイル画像を表示
- スワップ検出時にリアルタイム更新（サムネイルの位置を入れ替え）
- 直近スワップされたセルをハイライト表示

---

## 6. データフロー

### Phase 1: 初期配置記録

```
[画面キャプチャ（1枚）]
    → frame
    → GridDetector.detect(frame)
        → grid: N×M のセル座標
        → difficulty: 甘口/中辛/辛口/激辛
    → 各セルをcrop → ItemClassifier.register_from_grid()
        → テンプレート自動登録（ペア数分）
    → 各セルを分類 → PanelState.set_initial()
        → grid[row][col] = item_id（全セル）
    → GUI: パネル配置図にサムネイル表示
```

### Phase 2: シャッフル追跡

```
[連続キャプチャ 30fps]
    → ShuffleMonitor.process_frame(frame)
        [WAITING_FLIP]
            → 全体差分が大きい → 裏返しアニメーション中
            → 差分安定 → IDLE遷移、安定フレーム記録
        [IDLE]
            → 全体差分 > 1.5 → SWAPPING遷移
            → 安定フレーム更新
        [SWAPPING]
            → 最初のフレーム: 各セルdiff計算 → top2 = 交換セル
            → on_swap(cellA, cellB) 発火
                → PanelState.apply_swap()
                → GUI: 配置図更新
            → 安定状態復帰待ち
        [期待スワップ回数到達]
            → DONE遷移
            → on_complete() 発火
            → 連続キャプチャ停止
```

---

## 7. 技術的課題と対策

### 7.1 スワップ開始フレームの正確な検出

**課題**: top2方式はスワップ開始直後の1フレームで最も精度が高い。遅延するとノイズ増。

**対策**:
- 30fpsキャプチャなら安定→変化の遷移を1フレーム（33ms）以内に検出可能
- 安定判定の閾値は全体diff < 1.5（実測で安定期間のdiffは0.3〜0.5）
- 「変化検出した最初のフレーム」でtop2を取る

### 7.2 ウィンドウサイズ対応

**課題**: プレイヤーのウィンドウサイズにより全ピクセル値が変わる

**対策**:
- グリッド検出の面積フィルタを画像サイズに対する比率で計算
  - min_area = (画像面積 / パネル数 / 4)
  - max_area = (画像面積 / パネル数 * 3)
- グレースケール閾値(130)は相対値なので概ね不変
- テンプレートマッチングは同セッション内で一定のためスケール不変性は不要
- ウィンドウリサイズ時はPhase1からやり直し

### 7.3 難易度ごとのグリッドサイズ差

**課題**: グリッドが3×4〜4×6まで変わる

**対策**:
- GridDetector.detect()はグリッドサイズをハードコードせず動的検出
- 検出されたパネル数(12/16/20/24)から難易度・行列数・期待スワップ数を自動推定

### 7.4 特殊パネル

**課題**: チャンスパネル・シャッフルパネル・メタルスライムは通常アイテムと挙動が異なる

**対策**:
- 画像認識上は他のアイテムと同様に扱う（テンプレートの1つとして登録）
- 配置図上でサムネイル表示されるので、プレイヤーが視覚的に判別可能
- シャッフルパネルは配置がわかっていれば避けるだけなので特別対応不要

---

## 8. 技術スタック

| 項目 | 選定 | 理由 |
|------|------|------|
| 言語 | Python 3.12+ | OpenCV/画像処理ライブラリが豊富 |
| 画面キャプチャ | mss | 高速・クロスプラットフォーム |
| ウィンドウ検出 | pygetwindow | ウィンドウタイトルからの領域取得 |
| 画像処理 | OpenCV (cv2) | テンプレートマッチング・輪郭検出 |
| 数値計算 | NumPy | OpenCVの依存でもある |
| GUI | tkinter | Python標準・追加インストール不要 |

### 依存パッケージ
```
mss
opencv-python
numpy
pygetwindow
```

---

## 9. ファイル構成

```
lucky_panel_tracker/
├── main.py              # エントリーポイント
├── capture.py           # Screen Capture
├── grid.py              # Grid Detector
├── classifier.py        # Item Classifier
├── tracker.py           # State Tracker (PanelState)
├── monitor.py           # Shuffle Monitor
├── app.py               # GUI (tkinter)
├── requirements.txt
└── README.md
```

---

## 10. 開発ステップと成功条件

### Step 1: グリッド検出
- **入力**: `samples/phase1/full_face_up.png`
- **成功条件**: 4行×6列=24パネルのbboxが全て正しく検出される
- **検証**: `samples/debug_grid_final.png`と目視比較

### Step 2: アイテム分類
- **入力**: Step 1のcrop画像（`samples/crops/panel_r*_c*.png`）
- **成功条件**: 12種のテンプレートに正しくグルーピングされ、各2枚のペアになる
- **検証**: テンプレートマッチング結果のconfidence値が全ペアで > 0.85

### Step 3: スワップ検出
- **入力**: `samples/phase2_swap/`のフレーム群（またはshuffleフォルダの連番フレーム）
- **成功条件**: 7回のスワップが全て正しい2セルペアで検出される
- **期待結果**: Swap1=[0,5]↔[3,5], Swap2=[3,1]↔[1,0], Swap3=[0,2]↔[2,2], Swap4=[3,0]↔[3,3], Swap5=[0,4]↔[2,3], Swap6=[2,1]↔[0,3], Swap7=[3,5]↔[2,1]

### Step 4: 結合テスト
- **成功条件**: Phase1の初期配置にStep3の全スワップを適用した最終配置が、ゲーム内のプレイと一致

### Step 5: Screen Capture実装
- mssでの画面キャプチャ + ウィンドウ自動検出 or 手動領域指定

### Step 6: GUI実装
- tkinterでメインウィンドウ
- Phase1/Phase2ボタン + パネル配置図 + ステータス表示

### Step 7: リアルタイム結合テスト
- 実際のSteam版DQ7でエンドツーエンドテスト

---

## 11. サンプルデータ

設計書と同梱の`samples/`フォルダに以下が含まれる:

```
samples/
├── phase1/
│   └── full_face_up.png          # 全パネル表向き（Phase1入力）
├── phase2_back/
│   └── all_back.png              # 全パネル裏面（Phase2開始直前）
├── phase2_swap/
│   ├── swap1_start.png           # スワップ1 浮き始め
│   ├── swap1_mid.png             # スワップ1 移動中
│   ├── swap1_end.png             # スワップ1 着地寸前
│   ├── swap1_landed.png          # スワップ1 着地後
│   ├── swap2_start.png           # スワップ2 浮き始め
│   ├── swap2_mid.png             # スワップ2 移動中
│   ├── swap4_mid.png             # スワップ4 移動中
│   └── between_swaps.png         # スワップ間の安定状態
├── crops/
│   ├── panel_r0_c0.png ~ panel_r3_c5.png   # 各パネルのcrop画像（24枚）
├── debug_grid_final.png          # グリッド検出結果の可視化
├── debug_blue_mask.png           # 青色マスクの可視化
└── debug_white_mask.png          # 白色マスクの可視化
```

すべて640×360解像度。激辛（4×6, 24パネル, 7スワップ）の実データ。

---

## 12. 未確認事項

- [ ] カーソル出現の検出方法（Phase2完了判定のフォールバック用）
