"""
pre_upload_tab.py — Tab giao diện Quản lý Pre-Upload & Xuất bản YouTube (Phần 1 & 3).

Thiết kế:
  - Quét thư mục 0000_VID_DONE kiểm tra trạng thái 3/3 (Video Final {ID}.mp4, Metadata, Thumbnail).
  - Cho phép ghép clip ra {ID}.mp4 (validate 100% clip) và trích metadata.json / thumb.json local.
  - Đẩy kịch bản Thumb sang Queue Tạo Ảnh trên Dashboard.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils.pre_upload_ops import (
    scan_vid_done_status,
    merge_project_final_video,
    extract_metadata_and_thumb_json,
    transfer_to_vid_done
)

class PreUploadTab(ttk.Frame):
    ROW_EVEN  = "#2a2a2a"
    ROW_ODD   = "#252525"
    ROW_HOVER = "#333333"

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller # BatchApp

        self.project_vars: dict[str, tk.BooleanVar] = {}
        self.project_data: dict[str, dict] = {}
        self.project_names_ordered: list[str] = []

        self._build_ui()

    # ─────────────────────────────────────────────────────────────
    # BUILD UI
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────
        toolbar = ttk.Frame(self, padding=(12, 10, 12, 6))
        toolbar.pack(fill="x")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="📁 Thư mục 0000_VID_DONE:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8))

        self.entry_root = ttk.Entry(toolbar, font=("Segoe UI", 9))
        self.entry_root.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        ttk.Button(toolbar, text="📂 Browse", width=10,
                   command=self._browse_root).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(toolbar, text="🔍 QUÉT TÀI NGUYÊN", style="Accent.TButton", width=18,
                   command=self._scan_root).grid(row=0, column=3)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(6, 0))

        # ── Summary bar ──────────────────────────────────────────
        summary_bar = ttk.Frame(self, padding=(12, 6, 12, 6))
        summary_bar.pack(fill="x")

        self.lbl_status = ttk.Label(
            summary_bar,
            text="Chưa quét — chọn thư mục 0000_VID_DONE và nhấn 🔍 QUÉT TÀI NGUYÊN",
            foreground="#888", font=("Segoe UI", 9))
        self.lbl_status.pack(side="left")

        self.lbl_counter = ttk.Label(
            summary_bar, text="",
            foreground="#00d4ff", font=("Segoe UI", 9, "bold"))
        self.lbl_counter.pack(side="right")

        # ── Scrollable list ──────────────────────────────────────
        list_outer = ttk.Frame(self, padding=(8, 0, 8, 0))
        list_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_outer, highlightthickness=0, bg="#1e1e1e")
        scrollbar   = ttk.Scrollbar(list_outer, orient="vertical", command=self.canvas.yview)

        self.scroll_frame = tk.Frame(self.canvas, bg="#1e1e1e")
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self._canvas_win = self.canvas.create_window(
            (0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._canvas_win, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scroll_frame.bind("<MouseWheel>", self._on_mousewheel)

        # ── Log area ─────────────────────────────────────────────
        log_frame = ttk.LabelFrame(self, text=" 📜 Nhật ký Pre-Upload ", padding=(4, 4))
        log_frame.pack(fill="x", padx=12, pady=(4, 4))

        self.log_text = tk.Text(
            log_frame, height=5, wrap="word",
            bg="#1a1a1a", fg="#ccc", insertbackground="#ccc",
            font=("Consolas", 9), relief="flat", bd=0)
        self.log_text.pack(fill="x")

        self.log_text.tag_configure("SUCCESS", foreground="#6cc644")
        self.log_text.tag_configure("ERROR", foreground="#f85149")
        self.log_text.tag_configure("WARNING", foreground="#d29922")
        self.log_text.tag_configure("INFO", foreground="#58a6ff")

        # ── Action bar (Bulk Actions) ───────────────────────────
        action_bar = tk.Frame(self, bg="#252525", pady=8)
        action_bar.pack(fill="x", side="bottom")

        left_btns = ttk.Frame(action_bar)
        left_btns.pack(side="left", padx=12)
        ttk.Button(left_btns, text="☑ Select All", command=self._select_all, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(left_btns, text="☐ Cancel All", command=self._cancel_all, width=12).pack(side="left")

        right_btns = ttk.Frame(action_bar)
        right_btns.pack(side="right", padx=12)

        self.lbl_selected = ttk.Label(right_btns, text="0 đã chọn", foreground="#888", font=("Segoe UI", 9))
        self.lbl_selected.pack(side="left", padx=(0, 10))

        ttk.Button(right_btns, text="🎬 Ghép Video ({ID}.mp4)", command=self._bulk_merge_videos, width=22).pack(side="left", padx=(0, 6))
        ttk.Button(right_btns, text="📤 Pre Upload (Chuyển sang 0000_VID_DONE)", style="Accent.TButton", command=self._bulk_pre_upload, width=38).pack(side="left")

    def _log(self, msg, level="INFO"):
        def _append():
            tag = level if level in ("SUCCESS", "ERROR", "WARNING", "INFO") else "INFO"
            self.log_text.insert(tk.END, msg + "\n", tag)
            self.log_text.see(tk.END)
        self.log_text.after(0, _append)

    # ─────────────────────────────────────────────────────────────
    # SCAN & RENDER
    # ─────────────────────────────────────────────────────────────
    def _browse_root(self):
        d = filedialog.askdirectory(title="Chọn thư mục 0000_VID_DONE")
        if d:
            self.entry_root.delete(0, tk.END)
            self.entry_root.insert(0, d)
            self._scan_root()

    def _scan_root(self):
        root_path = self.entry_root.get().strip()
        if not root_path or not os.path.isdir(root_path):
            messagebox.showwarning("Lỗi", "Vui lòng chọn thư mục 0000_VID_DONE hợp lệ!")
            return

        self._clear_list()
        self.lbl_status.config(text="⏳ Đang quét tài nguyên...", foreground="#ffb86c")
        self.update_idletasks()

        results = scan_vid_done_status(root_path)
        if not results:
            self.lbl_status.config(text="⚠️ Thư mục trống hoặc không tìm thấy dự án nào.", foreground="#ff5555")
            return

        self.project_data = results

        # Thống kê
        n_complete = sum(1 for d in results.values() if d["is_complete"])
        n_miss_vid = sum(1 for d in results.values() if not d["has_video"])
        n_miss_meta = sum(1 for d in results.values() if not d["has_metadata"])
        n_miss_thumb = sum(1 for d in results.values() if not d["has_thumb"])

        stat_str = f"Tổng: {len(results)} dự án | 🟢 Hoàn thiện (3/3): {n_complete} | 🎬 Thiếu Clip: {n_miss_vid} | 📑 Thiếu Meta: {n_miss_meta} | 🎨 Thiếu Thumb: {n_miss_thumb}"
        self.lbl_status.config(text=stat_str, foreground="#6cc644" if n_complete == len(results) else "#ffb86c")

        for idx, (name, data) in enumerate(results.items()):
            self._add_project_row(idx, name, data)

        self._update_counter()
        self._log(f"🔍 Đã quét xong thư mục: {root_path} ({len(results)} dự án)", "SUCCESS")

    def _add_project_row(self, idx: int, name: str, data: dict):
        bg = self.ROW_EVEN if idx % 2 == 0 else self.ROW_ODD

        card = tk.Frame(self.scroll_frame, bg=bg, pady=6, padx=8)
        card.pack(fill="x")
        card.bind("<MouseWheel>", self._on_mousewheel)

        var = tk.BooleanVar(value=not data["is_complete"])
        self.project_vars[name] = var
        self.project_names_ordered.append(name)

        chk = ttk.Checkbutton(card, variable=var, cursor="hand2", command=self._update_counter)
        chk.pack(side="left", padx=(0, 4))

        tk.Label(card, text=f"{idx+1:>3}.", bg=bg, fg="#555", font=("Segoe UI", 9), width=3).pack(side="left", padx=(0, 6))

        # Folder ID
        vid_id = data["vid_id"]
        name_color = "#6cc644" if data["is_complete"] else "#ffffff"
        tk.Label(card, text=name, bg=bg, fg=name_color, font=("Segoe UI", 10, "bold"), width=16, anchor="w").pack(side="left", padx=(0, 8))

        # Badges 3 thành phần
        # 1. Video Final ({ID}.mp4)
        vid_txt = f"🎬 {vid_id}.mp4 ✅" if data["has_video"] else f"🎬 {vid_id}.mp4 ❌"
        vid_fg = "#6cc644" if data["has_video"] else "#ff5555"
        tk.Label(card, text=vid_txt, bg=bg, fg=vid_fg, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 10))

        # 2. Metadata (metadata.json)
        meta_txt = "📄 metadata.json ✅" if data["has_metadata"] else "📄 metadata.json ❌"
        meta_fg = "#6cc644" if data["has_metadata"] else "#ff5555"
        tk.Label(card, text=meta_txt, bg=bg, fg=meta_fg, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 10))

        # 3. Thumbnail
        thumb_txt = "🎨 Thumbnail ✅" if data["has_thumb"] else "🎨 Thumbnail ❌"
        thumb_fg = "#6cc644" if data["has_thumb"] else "#ff5555"
        tk.Label(card, text=thumb_txt, bg=bg, fg=thumb_fg, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 10))

        tk.Frame(self.scroll_frame, bg="#333333", height=1).pack(fill="x")

    # ─────────────────────────────────────────────────────────────
    # ACTION LOGIC
    # ─────────────────────────────────────────────────────────────
    def _bulk_merge_videos(self):
        selected = [n for n, v in self.project_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất 1 dự án!")
            return

        def _w():
            self._log(f"🚀 BẮT ĐẦU GHÉP HÀNG LOẠT {len(selected)} VIDEO...", "INFO")
            for n in selected:
                data = self.project_data[n]
                if data["has_video"]: continue
                ok, msg = merge_project_final_video(data["folder_path"], data["vid_id"], self._log)
                if ok: self._log(f"✅ [{n}] Ghép thành công: {data['vid_id']}.mp4", "SUCCESS")
                else: self._log(f"❌ [{n}] Lỗi: {msg}", "ERROR")
            self.after(0, self._scan_root)

        threading.Thread(target=_w, daemon=True).start()

    def _bulk_pre_upload(self):
        selected = [n for n, v in self.project_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn ít nhất 1 dự án!")
            return

        root_dir = self.entry_root.get().strip()
        parent_dir = os.path.dirname(root_dir) if os.path.basename(root_dir) in ["0001_input", "Script_raw"] else root_dir
        target_vid_done = os.path.join(parent_dir, "0000_VID_DONE")
        os.makedirs(target_vid_done, exist_ok=True)

        transferred = 0
        for n in selected:
            data = self.project_data[n]
            if not data.get("is_complete"):
                self._log(f"⚠️ [{n}] Bỏ qua vì chưa đủ 3/3 tài nguyên (Video/Meta/Thumb)!", "WARNING")
                continue

            ok, msg = transfer_to_vid_done(data, target_vid_done)
            if ok:
                transferred += 1
                self._log(f"🎉 [{n}] Đã chuyển 3/3 tài nguyên sang {msg}", "SUCCESS")
            else:
                self._log(f"❌ [{n}] {msg}", "ERROR")

        if transferred > 0:
            messagebox.showinfo("Thành công", f"Đã chuyển {transferred} dự án (3/3) sang {target_vid_done}!")
            self._scan_root()
        else:
            messagebox.showwarning("Chưa chuyển", "Không có dự án nào đủ 3/3 tài nguyên để chuyển!")

    # ─────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _select_all(self):
        for var in self.project_vars.values():
            var.set(True)
        self._update_counter()

    def _cancel_all(self):
        for var in self.project_vars.values():
            var.set(False)
        self._update_counter()

    def _update_counter(self):
        total    = len(self.project_vars)
        selected = sum(1 for v in self.project_vars.values() if v.get())
        self.lbl_selected.config(
            text=f"{selected} đã chọn",
            foreground="#00d4ff" if selected > 0 else "#888")
        self.lbl_counter.config(text=f"{selected} / {total}" if total else "")

    def _clear_list(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.project_vars.clear()
        self.project_data.clear()
        self.project_names_ordered.clear()
        self.lbl_counter.config(text="")
