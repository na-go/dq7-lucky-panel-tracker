# Lucky Panel Tracker

DQ7 リメイク (Steam版) のラッキーパネルをリアルタイム追跡するツール。
シャッフル中のパネル入れ替えを全て検出し、最終配置を表示します。

## 使い方

### exe版（推奨）

1. [Releases](https://github.com/na-go/dq7-lucky-panel-tracker/releases) から最新の `LuckyPanelTracker-vX.X.X.zip` をダウンロード
2. 解凍して `LuckyPanelTracker.exe` を実行

### Python実行

```bash
pip install -r requirements.txt
python main.py
```

## 操作手順

### 1. 領域設定

ゲーム内でラッキーパネルの画面を開いた状態で **[領域設定]** をクリック。
「DRAGON QUEST VII」ウィンドウを自動検出します。

> Windows Graphics Capture (WGC) に対応しているため、ゲームウィンドウの上に別のツールが重なっていても正しくキャプチャできます。

### 2. Phase1: 初期配置記録

パネルが全て表に向いている状態で **[Phase1: 初期配置記録]** をクリック。
グリッド検出 → アイテム分類が自動で行われ、パネル配置図にサムネイルが表示されます。

### 3. Phase2: シャッフル追跡

**[Phase2: シャッフル追跡]** をクリックしてから、ゲーム内でAボタンを押してシャッフルを開始。
スワップが検出されるたびにパネル配置図がリアルタイム更新されます。

### 4. 結果確認

全スワップ検出完了後、パネル配置図が最終配置を表示します。
この情報を見ながらパネルを選びましょう。

## 機能

- **自動ウィンドウ検出** — 「DRAGON QUEST VII」ウィンドウを自動検出
- **WGCキャプチャ** — 重なったウィンドウを無視してゲーム画面だけをキャプチャ (Windows 10 2004+)
- **グリッド自動検出** — OpenCVで4難易度 (甘口/中辛/辛口/激辛) のグリッドを自動検出
- **テンプレートマッチング** — アイテムの種類を画像類似度で自動分類
- **リアルタイム追跡** — 30fpsでフレーム差分を監視、スワップを即座に検出
- **最前面固定** — トラッカーを常に最前面に表示するトグルボタン

## 難易度対応

| 難易度 | グリッド | パネル数 | スワップ回数 |
|--------|---------|---------|------------|
| 甘口   | 3x4     | 12      | 2          |
| 中辛   | 4x4     | 16      | 3          |
| 辛口   | 4x5     | 20      | 5          |
| 激辛   | 4x6     | 24      | 7          |

## 動作環境

- Windows 10 バージョン 2004 以降 (WGCキャプチャ使用時)
- DQ7 リメイク Steam版 (ウィンドウモード)

## 技術スタック

- **GUI**: tkinter
- **画像処理**: OpenCV, NumPy
- **キャプチャ**: Windows Graphics Capture API (ctypes), mss (フォールバック)
- **ビルド**: PyInstaller
- **CI/CD**: GitHub Actions (タグpushで自動ビルド & リリース)

## アーキテクチャ

```
[領域設定] → ScreenCapture (WGC / mss)
    ↓
[Phase1]  → GridDetector → ItemClassifier → PanelState (初期配置)
    ↓
[Phase2]  → ShuffleMonitor (30fps差分検出) → PanelState (スワップ適用)
    ↓
[結果]    → パネル配置図 (最終配置)
```

## ライセンス

MIT
