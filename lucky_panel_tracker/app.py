"""GUI - tkinterベースのメインアプリケーション"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageTk

from .capture import ScreenCapture
from .grid import GridDetector, GridCell
from .classifier import ItemClassifier
from .tracker import PanelState
from .monitor import ShuffleMonitor


class App:
    PREVIEW_WIDTH = 400
    PREVIEW_HEIGHT = 225
    THUMB_SIZE = 56  # パネル配置図のサムネイルサイズ

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Lucky Panel Tracker")
        self.root.resizable(False, False)

        # コアモジュール
        self.capture = ScreenCapture()
        self.detector = GridDetector()
        self.classifier = ItemClassifier()
        self.state: Optional[PanelState] = None
        self.monitor: Optional[ShuffleMonitor] = None

        # Phase1結果
        self.grid: Optional[list[list[GridCell]]] = None
        self.difficulty: Optional[dict] = None
        self.thumbnails: dict[str, ImageTk.PhotoImage] = {}  # item_id -> PhotoImage
        self.mapping: dict[tuple[int, int], str] = {}

        # 最前面固定
        self._topmost = False

        # Phase2制御
        self._phase2_running = False
        self._phase2_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._update_status("起動完了。[領域設定]でゲームウィンドウを指定してください。")

    def _build_ui(self):
        # --- メインフレーム ---
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        # --- 上段: プレビュー + パネル配置図 ---
        top = ttk.Frame(main)
        top.pack(fill=tk.X, pady=(0, 8))

        # キャプチャプレビュー
        preview_frame = ttk.LabelFrame(top, text="キャプチャプレビュー", padding=4)
        preview_frame.pack(side=tk.LEFT, padx=(0, 8))
        self.preview_canvas = tk.Canvas(
            preview_frame, width=self.PREVIEW_WIDTH, height=self.PREVIEW_HEIGHT, bg="#333"
        )
        self.preview_canvas.pack()

        # パネル配置図
        panel_frame = ttk.LabelFrame(top, text="パネル配置図", padding=4)
        panel_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.panel_canvas = tk.Canvas(panel_frame, bg="#f0e6d0")
        self.panel_canvas.pack(fill=tk.BOTH, expand=True)

        # --- 中段: ステータス ---
        self.status_var = tk.StringVar(value="")
        status_label = ttk.Label(main, textvariable=self.status_var, relief=tk.SUNKEN, padding=4)
        status_label.pack(fill=tk.X, pady=(0, 8))

        # --- 下段: ボタン ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X)

        self.btn_region = ttk.Button(btn_frame, text="領域設定", command=self._on_region_setup)
        self.btn_region.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_phase1 = ttk.Button(btn_frame, text="Phase1: 初期配置記録", command=self._on_phase1, state=tk.DISABLED)
        self.btn_phase1.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_phase2 = ttk.Button(btn_frame, text="Phase2: シャッフル追跡", command=self._on_phase2, state=tk.DISABLED)
        self.btn_phase2.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_stop = ttk.Button(btn_frame, text="停止", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 4))

        self.btn_reset = ttk.Button(btn_frame, text="リセット", command=self._on_reset)
        self.btn_reset.pack(side=tk.LEFT)

        self.btn_topmost = ttk.Button(btn_frame, text="最前面: OFF", command=self._on_toggle_topmost)
        self.btn_topmost.pack(side=tk.RIGHT)

    # === 最前面固定 ===
    def _on_toggle_topmost(self):
        self._topmost = not self._topmost
        self.root.attributes('-topmost', self._topmost)
        self.btn_topmost.config(text=f"最前面: {'ON' if self._topmost else 'OFF'}")

    # === ステータス更新 ===
    def _update_status(self, text: str):
        self.status_var.set(text)

    # === 領域設定 ===
    def _on_region_setup(self):
        # まず自動検出を試みる
        if self.capture.auto_detect_window():
            left, top, w, h = self.capture.region
            if self.capture.using_wgc:
                mode = "WGC"
            else:
                err = getattr(self.capture, '_wgc_error', None)
                mode = f"mss (WGC失敗: {err})" if err else "mss"
            self._update_status(f"ウィンドウ自動検出: {w}x{h} at ({left},{top}) [{mode}]")
            self.btn_phase1.config(state=tk.NORMAL)
            self._show_preview()
            return

        # 自動検出失敗 → 手動入力ダイアログ
        dialog = tk.Toplevel(self.root)
        dialog.title("キャプチャ領域設定")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="ゲームウィンドウが見つかりませんでした。\n手動でキャプチャ領域を入力してください。", padding=8).pack()

        form = ttk.Frame(dialog, padding=8)
        form.pack()

        labels = ["Left:", "Top:", "Width:", "Height:"]
        entries = []
        defaults = ["0", "0", "640", "360"]
        for i, (lbl, default) in enumerate(zip(labels, defaults)):
            ttk.Label(form, text=lbl).grid(row=i, column=0, sticky=tk.E, padx=(0, 4))
            e = ttk.Entry(form, width=10)
            e.insert(0, default)
            e.grid(row=i, column=1)
            entries.append(e)

        def apply():
            try:
                vals = tuple(int(e.get()) for e in entries)
                self.capture.set_region(vals)
                self._update_status(f"手動設定: {vals[2]}x{vals[3]} at ({vals[0]},{vals[1]})")
                self.btn_phase1.config(state=tk.NORMAL)
                dialog.destroy()
                self._show_preview()
            except ValueError:
                messagebox.showerror("エラー", "数値を入力してください", parent=dialog)

        ttk.Button(dialog, text="適用", command=apply).pack(pady=8)

    def _show_preview(self):
        """現在のキャプチャ領域をプレビュー表示"""
        frame = self.capture.grab()
        if frame is None:
            return
        self._display_frame_on_preview(frame)

    def _display_frame_on_preview(self, frame: np.ndarray):
        """BGRフレームをプレビューキャンバスに表示"""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        pil_img = pil_img.resize((self.PREVIEW_WIDTH, self.PREVIEW_HEIGHT), Image.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(pil_img)
        self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self._preview_photo)

    # === Phase 1 ===
    def _on_phase1(self):
        self._update_status("Phase1: キャプチャ中...")
        frame = self.capture.grab()
        if frame is None:
            self._update_status("エラー: キャプチャ失敗")
            return

        self._display_frame_on_preview(frame)

        # グリッド検出
        try:
            self.grid = self.detector.detect(frame)
        except Exception as e:
            self._update_status(f"エラー: グリッド検出失敗 - {e}")
            return

        self.difficulty = self.detector.detect_difficulty(self.grid)
        rows = len(self.grid)
        cols = len(self.grid[0]) if self.grid else 0

        # アイテム分類
        self.classifier = ItemClassifier()
        self.mapping = self.classifier.register_from_grid(frame, self.grid)

        # PanelState初期化
        self.state = PanelState(rows, cols)
        for (r, c), item_id in self.mapping.items():
            self.state.set_initial(r, c, item_id)

        # サムネイル生成
        self.thumbnails.clear()
        for tmpl in self.classifier.templates:
            rgb = cv2.cvtColor(tmpl.thumbnail, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb).resize((self.THUMB_SIZE, self.THUMB_SIZE), Image.LANCZOS)
            self.thumbnails[tmpl.item_id] = ImageTk.PhotoImage(pil_img)

        # 配置図更新
        self._update_panel_view()

        n_templates = len(self.classifier.templates)
        n_pairs = sum(1 for t in self.classifier.templates if len(t.positions) == 2)
        n_special = sum(1 for t in self.classifier.templates if len(t.positions) == 1)

        self._update_status(
            f"Phase1完了: {self.difficulty['name']} ({rows}x{cols}), "
            f"{n_templates}種 ({n_pairs}ペア + {n_special}特殊), "
            f"期待スワップ: {self.difficulty['swaps']}回"
        )
        self.btn_phase2.config(state=tk.NORMAL)

    # === パネル配置図更新 ===
    def _update_panel_view(self, highlight: Optional[tuple] = None):
        """パネル配置図をサムネイルで描画"""
        if self.state is None or self.grid is None:
            return

        canvas = self.panel_canvas
        canvas.delete("all")

        rows = self.state.rows
        cols = self.state.cols
        pad = 3
        size = self.THUMB_SIZE
        total_w = cols * (size + pad) + pad
        total_h = rows * (size + pad) + pad
        canvas.config(width=total_w, height=total_h)

        self._panel_photos = []  # 参照保持

        for r in range(rows):
            for c in range(cols):
                x = pad + c * (size + pad)
                y = pad + r * (size + pad)
                item_id = self.state.grid[r][c]

                # 背景（ハイライト）
                if highlight and (r, c) in highlight:
                    canvas.create_rectangle(x - 2, y - 2, x + size + 2, y + size + 2,
                                            fill="#FF6B6B", outline="#FF0000", width=2)

                if item_id and item_id in self.thumbnails:
                    photo = self.thumbnails[item_id]
                    canvas.create_image(x, y, anchor=tk.NW, image=photo)
                    self._panel_photos.append(photo)
                else:
                    canvas.create_rectangle(x, y, x + size, y + size,
                                            fill="#cccccc", outline="#999999")

    # === Phase 2 ===
    def _on_phase2(self):
        if self.grid is None or self.difficulty is None or self.state is None:
            self._update_status("エラー: 先にPhase1を実行してください")
            return

        self.monitor = ShuffleMonitor(self.grid, self.difficulty["swaps"])
        self.monitor.on_swap = self._on_swap_detected
        self.monitor.on_complete = self._on_shuffle_complete

        self._phase2_running = True
        self.btn_phase2.config(state=tk.DISABLED)
        self.btn_phase1.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self._update_status("Phase2: シャッフル追跡中... ゲーム内でAボタンを押してシャッフル開始してください")

        self._phase2_thread = threading.Thread(target=self._phase2_loop, daemon=True)
        self._phase2_thread.start()

    def _phase2_loop(self):
        """Phase2のメインループ（別スレッド）"""
        for frame in self.capture.grab_continuous(fps=60):
            if not self._phase2_running:
                break
            self.monitor.process_frame(frame)

            # プレビュー更新（間引き）
            if self.monitor.swap_count % 1 == 0:
                self.root.after(0, self._display_frame_on_preview, frame)

    def _on_swap_detected(self, pos_a: tuple, pos_b: tuple, count: int):
        """スワップ検出コールバック（Phase2スレッドから呼ばれる）"""
        self.state.apply_swap(pos_a, pos_b)
        highlight = {pos_a, pos_b}
        self.root.after(0, self._update_panel_view, highlight)
        self.root.after(0, self._update_status,
                        f"Phase2追跡中: スワップ {count}/{self.difficulty['swaps']} 検出 "
                        f"[{pos_a[0]},{pos_a[1]}] ↔ [{pos_b[0]},{pos_b[1]}]")

    def _on_shuffle_complete(self):
        """シャッフル完了コールバック"""
        self._phase2_running = False
        self.root.after(0, self._update_panel_view)
        self.root.after(0, self._update_status,
                        f"シャッフル完了！ {self.difficulty['swaps']}回のスワップを全て検出しました。")
        self.root.after(0, self._finish_phase2)

    def _finish_phase2(self):
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_phase1.config(state=tk.NORMAL)
        self.btn_phase2.config(state=tk.DISABLED)

    # === 停止 / リセット ===
    def _on_stop(self):
        self._phase2_running = False
        self._update_status("Phase2: 手動停止")
        self._finish_phase2()

    def _on_reset(self):
        self._phase2_running = False
        self.grid = None
        self.difficulty = None
        self.state = None
        self.monitor = None
        self.classifier = ItemClassifier()
        self.thumbnails.clear()
        self.mapping.clear()
        self.panel_canvas.delete("all")
        self.preview_canvas.delete("all")
        self.btn_phase1.config(state=tk.DISABLED if self.capture.region is None else tk.NORMAL)
        self.btn_phase2.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.DISABLED)
        self._update_status("リセット完了。")

    # === 起動 ===
    def run(self):
        self.root.mainloop()
