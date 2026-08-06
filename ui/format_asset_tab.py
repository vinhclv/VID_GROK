"""
format_asset_tab.py — Tab giao diện Format Asset (2 pha).

Thiết kế: 1 root path + 2 nút bấm tuần tự.
Logic nghiệp vụ nằm ở utils/format_asset_ops.py.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils.format_asset_ops import (
    scan_project,
    phase1_split_and_build,
    phase2_distribute_and_deploy,
)


class FormatAssetTab(ttk.Frame):

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self._project_info = None
        self._build_ui()

    # ═════════════════════════════════════════════════════════
    # BUILD UI
    # ═════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Toolbar: root path ────────────────────────────
        toolbar = ttk.Frame(self, padding=(12, 10, 12, 4))
        toolbar.pack(fill="x")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="📁 Root:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 6))

        self.entry_root = ttk.Entry(toolbar, font=("Segoe UI", 9))
        self.entry_root.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        ttk.Button(toolbar, text="Browse", width=8,
                   command=self._browse).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(toolbar, text="QUÉT", style="Accent.TButton", width=8,
                   command=self._scan).grid(row=0, column=3)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(6, 0))

        # ── Info panel ────────────────────────────────────
        info_frame = ttk.LabelFrame(self, text=" Thông tin dự án ",
                                    padding=(12, 6, 12, 6))
        info_frame.pack(fill="x", padx=12, pady=(8, 4))

        self.lbl_info = ttk.Label(
            info_frame,
            text="Chưa quét — chọn thư mục và nhấn QUÉT",
            foreground="#888", font=("Segoe UI", 9),
            wraplength=800, justify="left")
        self.lbl_info.pack(anchor="w")

        # ── 2 pha (scrollable) ────────────────────────────
        phases_outer = ttk.Frame(self)
        phases_outer.pack(fill="both", expand=True, padx=12, pady=4)

        canvas = tk.Canvas(phases_outer, highlightthickness=0, bg="#1e1e1e")
        sb = ttk.Scrollbar(phases_outer, orient="vertical", command=canvas.yview)
        self._phases_frame = tk.Frame(canvas, bg="#1e1e1e")
        self._phases_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self._phases_frame, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Mousewheel
        def _mw(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _mw)
        self._phases_frame.bind("<MouseWheel>", _mw)

        self._build_phase_cards()

        # ── Log area ──────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text=" 📜 Nhật ký ", padding=(4, 4))
        log_frame.pack(fill="x", padx=12, pady=(4, 8))

        self.log_text = tk.Text(
            log_frame, height=8, wrap="word",
            bg="#1a1a1a", fg="#ccc", insertbackground="#ccc",
            font=("Consolas", 9), relief="flat", bd=0)
        self.log_text.pack(fill="x")

        self.log_text.tag_configure("SUCCESS", foreground="#6cc644")
        self.log_text.tag_configure("ERROR", foreground="#f85149")
        self.log_text.tag_configure("WARNING", foreground="#d29922")
        self.log_text.tag_configure("INFO", foreground="#58a6ff")

    def _build_phase_cards(self):
        """Tạo 2 card cho 2 pha."""
        phases = [
            {
                "title": "PHA 1 — Split & Build tham chiếu",
                "desc":  "Tách Script_raw → thư mục thành phần → Gộp character → tong_hop_character/",
                "btn":   "▶ SPLIT & BUILD",
                "cmd":   self._run_phase1,
                "color": "#2ac3de",
            },
            {
                "title": "PHA 2 — Phân phối ảnh & Deploy → 0001_input",
                "desc":  "Copy ảnh từ output_image/ → character/ & Đóng gói Storyboard JSON + Tài nguyên phụ vào 0001_input/{ID}/",
                "btn":   "▶ PHÂN PHỐI & DEPLOY",
                "cmd":   self._run_phase2,
                "color": "#7aa2f7",
            },
        ]

        self._phase_btns = []
        for i, p in enumerate(phases):
            card = tk.Frame(self._phases_frame, bg="#252525", bd=0,
                            highlightthickness=1, highlightbackground="#333")
            card.pack(fill="x", padx=4, pady=(6, 2))
            card.bind("<MouseWheel>", lambda e: self._phases_frame.event_generate("<MouseWheel>", delta=e.delta))

            # Header row
            header = tk.Frame(card, bg="#252525")
            header.pack(fill="x", padx=10, pady=(8, 2))

            tk.Label(header, text=p["title"],
                     bg="#252525", fg=p["color"],
                     font=("Segoe UI", 10, "bold")).pack(side="left")

            btn = ttk.Button(header, text=p["btn"],
                             style="Accent.TButton", width=22,
                             command=p["cmd"])
            btn.pack(side="right")
            self._phase_btns.append(btn)

            # Description
            tk.Label(card, text=p["desc"],
                     bg="#252525", fg="#999",
                     font=("Segoe UI", 8), anchor="w").pack(
                fill="x", padx=10, pady=(0, 8))

            # Arrow giữa các pha
            if i < len(phases) - 1:
                tk.Label(self._phases_frame, text="↓",
                         bg="#1e1e1e", fg="#555",
                         font=("Segoe UI", 12)).pack(pady=4)

    # ═════════════════════════════════════════════════════════
    # LOG
    # ═════════════════════════════════════════════════════════

    def _log(self, msg, level="INFO"):
        """Ghi log vào text widget (thread-safe)."""
        def _append():
            tag = level if level in ("SUCCESS", "ERROR", "WARNING", "INFO") else "INFO"
            self.log_text.insert(tk.END, msg + "\n", tag)
            self.log_text.see(tk.END)
        self.log_text.after(0, _append)

    # ═════════════════════════════════════════════════════════
    # EVENTS
    # ═════════════════════════════════════════════════════════

    def _browse(self):
        d = filedialog.askdirectory(title="Chọn thư mục gốc dự án")
        if d:
            self.entry_root.delete(0, tk.END)
            self.entry_root.insert(0, d)
            self._scan()

    def _get_root(self) -> str | None:
        root = self.entry_root.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showwarning("Lỗi", "Vui lòng chọn thư mục gốc hợp lệ!")
            return None
        return root

    def _scan(self):
        root = self._get_root()
        if not root:
            return

        info = scan_project(root)
        self._project_info = info

        lines = []
        lines.append(f"📄 Script_raw: {info['script_raw_count']} file")
        if info["script_ids"]:
            lines.append(f"📌 IDs: {', '.join(info['script_ids'][:20])}")
        lines.append(f"🖼️ tong_hop_character: {'✅ Có' if info['has_tong_hop'] else '❌ Chưa có'}")
        lines.append(f"🎨 Ảnh tham chiếu: {info['ref_image_count']} file")
        lines.append(f"📦 0001_input: {len(info['input_ids'])} dự án")

        self.lbl_info.config(text=" │ ".join(lines), foreground="#ccc")
        self._log(f"📂 Quét: {root}", "INFO")

    # ── Phase runners (threaded) ──────────────────────────

    def _run_in_thread(self, func, phase_idx):
        """Chạy func trong thread riêng, disable nút trong lúc chạy."""
        root = self._get_root()
        if not root:
            return

        btn = self._phase_btns[phase_idx]
        original_text = btn.cget("text")
        btn.config(state="disabled", text="⏳ Đang chạy...")

        def _worker():
            try:
                func(root, self._log)
            except Exception as e:
                self._log(f"❌ Lỗi nghiêm trọng: {e}", "ERROR")
            finally:
                self.after(0, lambda: btn.config(state="normal", text=original_text))
                self.after(0, self._scan)  # Refresh info

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _run_phase1(self):
        self.log_text.delete("1.0", tk.END)
        self._log("━━━ PHA 1: SPLIT & BUILD THAM CHIẾU ━━━", "INFO")
        self._run_in_thread(phase1_split_and_build, 0)

    def _run_phase2(self):
        self.log_text.delete("1.0", tk.END)
        self._log("━━━ PHA 2: PHÂN PHỐI ẢNH & DEPLOY TÀI NGUYÊN ━━━", "INFO")
        self._run_in_thread(phase2_distribute_and_deploy, 1)
