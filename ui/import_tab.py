import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import config


# ───────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# CONFIG DICT: Thêm mode mới = thêm 1 entry vào đây, không đụng code logic
# ─────────────────────────────────────────────────────────────────────────────
IMPORT_MODES = {
    "Prompt ➡ Image": {
        "required_subdirs":  ["character"],
        "input2_folder":     "character",
        "output_folder":     "output_image",
        "auto_create_out":   True,
        "badges":            ["📸 character/", "📤 output_image/ (auto)"],
        "loop_type":         "prompt_image",
        "need_gem":          True,
        "validate_timecode": False,
    },
    "Image ➡ Video": {
        "required_subdirs":  ["output_image"],
        "input2_folder":     "output_image",
        "output_folder":     "output_video",
        "auto_create_out":   True,
        "badges":            ["📸 output_image/", "📤 output_video/ (auto)"],
        "loop_type":         "image_to_video",
        "need_gem":          False,
        "validate_timecode": True,
    },
    "Image + Prompt ➡ Video": {
        "required_subdirs":  ["character", "output"],
        "input2_folder":     "character",
        "output_folder":     "output",
        "auto_create_out":   False,
        "badges":            ["📸 character/", "📤 output/"],
        "loop_type":         "1_image_prompt_video",
        "need_gem":          True,
        "validate_timecode": True,   # Kiểm tra timecode trong JSON khi quét
    },
    "Video ➡ Stretch (Timecode)": {
        "required_subdirs":  ["output"],
        "input2_folder":     "output",
        "output_folder":     "final",
        "auto_create_out":   True,
        "badges":            ["🎬 output/", "📤 final/ (auto)"],
        "loop_type":         "stretch_video",
        "need_gem":          False,
        "validate_timecode": True,   # Kiểm tra timecode trong JSON khi quét
    },
}


class ImportProjectTab(ttk.Frame):
    """
    Tab bulk-import nhiều project vào Queue.
    Hỗ trợ nhiều mode — mỗi mode được định nghĩa trong IMPORT_MODES.
    Thêm tính năng mới: chỉ cần thêm entry vào IMPORT_MODES.
    """

    ROW_EVEN  = "#2a2a2a"
    ROW_ODD   = "#252525"
    ROW_HOVER = "#333333"

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller  # BatchApp

        # {folder_name: tk.BooleanVar}
        self.folder_vars: dict[str, tk.BooleanVar] = {}
        # {folder_name: {"json": path, "subdirs": {name: path}, "cfg": dict}}
        self.folder_data: dict[str, dict] = {}

        self.selected_mode = tk.StringVar(value=list(IMPORT_MODES.keys())[0])

        self._build_ui()

    # ─────────────────────────────────────────────
    # BUILD UI
    # ─────────────────────────────────────────────
    def _build_ui(self):
        # ── Toolbar ──────────────────────────────
        toolbar = ttk.Frame(self, padding=(12, 10, 12, 6))
        toolbar.pack(fill="x")
        toolbar.columnconfigure(1, weight=1)

        # Row 0: đường dẫn + Browse + Quét
        ttk.Label(toolbar, text="Thư mục gốc:", font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", padx=(0, 8))

        self.entry_root = ttk.Entry(toolbar, font=("Segoe UI", 9))
        self.entry_root.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        ttk.Button(toolbar, text="📂 Browse", width=10,
                   command=self._browse_root).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(toolbar, text="🔍 QUÉT", style="Accent.TButton", width=10,
                   command=self._scan_root).grid(row=0, column=3)

        # Row 1: chọn mode
        ttk.Label(toolbar, text="Chế độ:", font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))

        self.cbo_mode = ttk.Combobox(
            toolbar,
            textvariable=self.selected_mode,
            values=list(IMPORT_MODES.keys()),
            state="readonly",
            font=("Segoe UI", 9),
            width=35,
        )
        self.cbo_mode.grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.cbo_mode.bind("<<ComboboxSelected>>", self._on_mode_change)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(4, 0))

        # ── Summary bar ──────────────────────────
        summary_bar = ttk.Frame(self, padding=(12, 5, 12, 3))
        summary_bar.pack(fill="x")

        self.lbl_status = ttk.Label(
            summary_bar,
            text="Chưa quét — chọn thư mục và nhấn 🔍 QUÉT",
            foreground="#888", font=("Segoe UI", 9))
        self.lbl_status.pack(side="left")

        self.lbl_counter = ttk.Label(
            summary_bar, text="",
            foreground="#00d4ff", font=("Segoe UI", 9, "bold"))
        self.lbl_counter.pack(side="right")

        # ── Scrollable list ───────────────────────
        list_outer = ttk.Frame(self, padding=(8, 0, 8, 0))
        list_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(list_outer, highlightthickness=0, bg="#1e1e1e")
        scrollbar   = ttk.Scrollbar(list_outer, orient="vertical",
                                    command=self.canvas.yview)

        self.scroll_frame = tk.Frame(self.canvas, bg="#1e1e1e")
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))

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

        # ── Action bar ────────────────────────────
        action_bar = tk.Frame(self, bg="#252525", pady=8)
        action_bar.pack(fill="x", side="bottom")

        left_btns = ttk.Frame(action_bar)
        left_btns.pack(side="left", padx=12)
        ttk.Button(left_btns, text="☑ Select All",
                   command=self._select_all, width=14).pack(side="left", padx=(0, 6))
        ttk.Button(left_btns, text="☐ Cancel All",
                   command=self._cancel_all, width=14).pack(side="left")

        right_btns = ttk.Frame(action_bar)
        right_btns.pack(side="right", padx=12)

        self.lbl_selected = ttk.Label(
            right_btns, text="0 đã chọn",
            foreground="#888", font=("Segoe UI", 9))
        self.lbl_selected.pack(side="left", padx=(0, 12))

        self.btn_add = ttk.Button(
            right_btns,
            text="⬇ ADD TO QUEUE",
            style="Accent.TButton",
            width=18,
            command=self._add_to_queue,
            state="disabled",
        )
        self.btn_add.pack(side="left")

    # ─────────────────────────────────────────────
    # MODE CHANGE
    # ─────────────────────────────────────────────
    def _on_mode_change(self, _event=None):
        """Đổi mode → clear list cũ để tránh hiện kết quả sai mode."""
        self._clear_list()
        self.lbl_status.config(
            text="Đã đổi chế độ — nhấn 🔍 QUÉT lại.",
            foreground="#888")

    # ─────────────────────────────────────────────
    # SCAN
    # ─────────────────────────────────────────────
    def _browse_root(self):
        d = filedialog.askdirectory(title="Chọn thư mục gốc chứa các Project")
        if d:
            self.entry_root.delete(0, tk.END)
            self.entry_root.insert(0, d)
            self._scan_root()

    def _scan_root(self):
        root_path = self.entry_root.get().strip()
        if not root_path or not os.path.isdir(root_path):
            messagebox.showwarning("Thiếu đường dẫn",
                                   "Vui lòng chọn thư mục gốc hợp lệ!")
            return

        cfg = IMPORT_MODES[self.selected_mode.get()]
        self._clear_list()
        self.lbl_status.config(text="⏳ Đang quét...", foreground="#ffb86c")
        self.update_idletasks()

        valid = self._find_valid_folders(root_path, cfg)

        if not valid:
            req = " + ".join(f"'{s}/'" for s in cfg["required_subdirs"])
            self.lbl_status.config(
                text=f"⚠️  Không tìm thấy project hợp lệ. Cần: 1 file .json, {req}",
                foreground="#ff5555")
            self.lbl_counter.config(text="")
            self.btn_add.config(state="disabled")
            return

        self.lbl_status.config(
            text=f"✅  Tìm thấy {len(valid)} project hợp lệ.",
            foreground="#6cc644")

        for idx, (name, data) in enumerate(valid.items()):
            self._add_folder_row(idx, name, data, cfg)

        self.folder_data = valid
        self._update_counter()
        self.btn_add.config(state="normal")

        # Log tất cả lỗi timecode xuống nhật ký
        for name, data in valid.items():
            if not data.get("tc_ok", True):
                bad_stts = data.get("tc_bad_stts", [])
                if bad_stts:
                    stts_str = ", ".join(bad_stts)
                    self.controller.log(
                        f"⚠️  [{name}] Timecode sai định dạng — STT lỗi: {stts_str}",
                        "WARNING"
                    )
                else:
                    # Lỗi khác (vd: không đọc được file JSON)
                    tc_err   = data.get("tc_err", "")
                    err_line = tc_err.splitlines()[0].strip() if tc_err else "Lỗi không xác định"
                    self.controller.log(
                        f"⚠️  [{name}] {err_line}",
                        "WARNING"
                    )


    def _find_valid_folders(self, root_path: str, cfg: dict) -> dict:
        """
        Generic scanner: hợp lệ khi có đúng 1 .json và tất cả required_subdirs tồn tại.
        Trả về {folder_name: {"json": path, "subdirs": {name: path}}}
        """
        result = {}
        try:
            entries = sorted(
                os.listdir(root_path),
                key=lambda x: (not x.isdigit(), x.zfill(10))
            )
        except PermissionError:
            messagebox.showerror("Lỗi", "Không có quyền đọc thư mục này!")
            return result

        for name in entries:
            folder_path = os.path.join(root_path, name)
            if not os.path.isdir(folder_path):
                continue

            # Kiểm tra từng required_subdir
            found_subdirs = {}
            for sub in cfg["required_subdirs"]:
                path = self._find_subdir(folder_path, sub)
                if not path:
                    break
                found_subdirs[sub] = path
            else:
                # Tìm đúng 1 file .json
                json_files = [
                    f for f in os.listdir(folder_path)
                    if f.lower().endswith(".json")
                    and os.path.isfile(os.path.join(folder_path, f))
                ]
                if len(json_files) == 1:
                    json_path = os.path.join(folder_path, json_files[0])

                    # Validate timecode nếu mode yêu cầu
                    tc_ok      = True
                    tc_err     = ""
                    tc_bad_stts = []
                    if cfg.get("validate_timecode"):
                        import re as _re
                        from utils.validators import validate_timecodes
                        tc_ok, tc_err = validate_timecodes(json_path)
                        if not tc_ok:
                            # Parse ra danh sách STT từ thông báo lỗi
                            tc_bad_stts = _re.findall(r'STT (\S+?):', tc_err)

                    result[name] = {
                        "json":         json_path,
                        "subdirs":      found_subdirs,
                        "root":         folder_path,
                        "tc_ok":        tc_ok,
                        "tc_err":       tc_err,
                        "tc_bad_stts":  tc_bad_stts,
                    }

        return result

    @staticmethod
    def _find_subdir(parent: str, target_name: str) -> str:
        """Tìm subfolder trong parent, so sánh case-insensitive."""
        try:
            for entry in os.listdir(parent):
                if entry.lower() == target_name.lower():
                    full = os.path.join(parent, entry)
                    if os.path.isdir(full):
                        return full
        except PermissionError:
            pass
        return ""

    # ─────────────────────────────────────────────
    # RENDER ROWS
    # ─────────────────────────────────────────────
    def _add_folder_row(self, idx: int, name: str, data: dict, cfg: dict):
        tc_ok  = data.get("tc_ok", True)
        tc_err = data.get("tc_err", "")
        bg = self.ROW_EVEN if idx % 2 == 0 else self.ROW_ODD

        card = tk.Frame(self.scroll_frame, bg=bg, pady=5, padx=8)
        card.pack(fill="x")
        card.bind("<MouseWheel>", self._on_mousewheel)
        card.bind("<Enter>",  lambda e, f=card: f.config(bg=self.ROW_HOVER))
        card.bind("<Leave>",  lambda e, f=card, b=bg: f.config(bg=b))

        # Checkbox — disabled nếu timecode sai
        var = tk.BooleanVar(value=tc_ok)   # sử lý: sai thì uncheck luôn
        self.folder_vars[name] = var

        chk = ttk.Checkbutton(card, variable=var,
                               command=self._update_counter, cursor="hand2")
        if not tc_ok:
            chk.state(["disabled"])        # disable, không cho chọn
        chk.pack(side="left", padx=(0, 4))

        # STT
        tk.Label(card, text=f"{idx+1:>3}.", bg=bg,
                 fg="#555", font=("Segoe UI", 9), width=3).pack(side="left", padx=(0, 6))

        # Folder name — vàng nếu lỗi, trắng nếu ok
        name_color = "#ffaa00" if not tc_ok else "#e0e0e0"
        tk.Label(card, text=name, bg=bg,
                 fg=name_color, font=("Segoe UI", 10, "bold"),
                 width=20, anchor="w").pack(side="left", padx=(0, 12))

        # JSON filename
        json_name = os.path.basename(data["json"])
        json_disp = (json_name[:22] + "…") if len(json_name) > 24 else json_name
        tk.Label(card, text=f"📄 {json_disp}", bg=bg,
                 fg="#cccccc", font=("Consolas", 8),
                 width=26, anchor="w").pack(side="left", padx=(0, 10))

        if tc_ok:
            # Badges bình thường
            for label in cfg["badges"]:
                tk.Label(card, text=label, bg=bg,
                         fg="#aaaaaa", font=("Segoe UI", 8)).pack(side="left", padx=(0, 10))
        else:
            # Hiển thị các STT bị lỗi
            bad_stts = data.get("tc_bad_stts", [])
            if bad_stts:
                stts_str = ", ".join(bad_stts[:8])
                suffix   = f" (+{len(bad_stts)-8} nữa)" if len(bad_stts) > 8 else ""
                warn_txt = f"⚠️ STT lỗi: {stts_str}{suffix}"
            else:
                warn_txt = "⚠️ Timecode sai định dạng"
            tk.Label(card, text=warn_txt, bg=bg,
                     fg="#ffaa00", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))

        # Path gốc (dim, right-aligned)
        root_disp = self._short_path(data["root"])
        tk.Label(card, text=root_disp, bg=bg,
                 fg="#444", font=("Segoe UI", 7), anchor="e").pack(
            side="right", padx=(8, 0))

        # Separator
        tk.Frame(self.scroll_frame, bg="#333333", height=1).pack(fill="x")


    @staticmethod
    def _short_path(path: str, max_len: int = 45) -> str:
        if len(path) <= max_len:
            return path
        half = (max_len - 3) // 2
        return path[:half] + "…" + path[-half:]

    # ─────────────────────────────────────────────
    # CONTROLS
    # ─────────────────────────────────────────────
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _select_all(self):
        for var in self.folder_vars.values():
            var.set(True)
        self._update_counter()

    def _cancel_all(self):
        for var in self.folder_vars.values():
            var.set(False)
        self._update_counter()

    def _update_counter(self):
        total    = len(self.folder_vars)
        selected = sum(1 for v in self.folder_vars.values() if v.get())
        self.lbl_selected.config(
            text=f"{selected} đã chọn",
            foreground="#00d4ff" if selected > 0 else "#888")
        self.lbl_counter.config(text=f"{selected} / {total}" if total else "")

    def _clear_list(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.folder_vars.clear()
        self.folder_data.clear()
        self.lbl_counter.config(text="")
        self.btn_add.config(state="disabled")

    # ─────────────────────────────────────────────
    # ADD TO QUEUE
    # ─────────────────────────────────────────────
    def _add_to_queue(self):
        selected = [n for n, v in self.folder_vars.items() if v.get()]
        if not selected:
            messagebox.showwarning("Chưa chọn",
                                   "Vui lòng chọn ít nhất 1 project!")
            return

        cfg = IMPORT_MODES[self.selected_mode.get()]

        # ── Lấy GEM và URL từ gem["url"] ───────────────
        gem_name = ""
        url      = ""
        if cfg["need_gem"]:

            gems = config.global_settings.get("gems", [])
            if not gems:
                messagebox.showwarning(
                    "Chưa có GEM",
                    "Chưa có GEM nào trong Settings!\n"
                    "Vui lòng thêm GEM trước (Tab ⚙️ Cài đặt).")
                return
            grok_gems = [g for g in gems if "grok" in g.get("name", "").lower()]
            gem       = grok_gems[0] if grok_gems else gems[0]
            gem_name  = gem["name"]
            url       = gem.get("url", "")    # ← URL lấy từ GEM, không phải videofx_url
        else:
            gem_name = "Local FFmpeg"         # Stretch mode: FFmpeg local

        # ── Add từng project ─────────────────────
        dashboard = self.controller.tab_dashboard
        count = 0

        for name in selected:
            if name not in self.folder_data:
                continue
            data = self.folder_data[name]

            # Bỏ qua nếu timecode sai (checkbox đã disabled nhưng guard chắc chắn)
            if not data.get("tc_ok", True):
                continue

            # input2: folder nguồn (character/ hoặc output/)
            inp2 = data["subdirs"].get(cfg["input2_folder"], "")

            # output: folder đích (output/ hoặc final/)
            out = os.path.join(data["root"], cfg["output_folder"])

            # Tạo output folder nếu mode yêu cầu
            if cfg["auto_create_out"] and out:
                os.makedirs(out, exist_ok=True)

            dashboard.add_project_direct(
                inp      = data["json"],
                inp2     = inp2,
                out      = out,
                url      = url,
                gem_name = gem_name,
            )
            count += 1


        mode_label = self.selected_mode.get()

        # Switch về Dashboard và tự động đồng bộ chế độ chạy
        dashboard = self.controller.tab_dashboard
        dashboard.selected_mode.set(mode_label)
        dashboard.cbo_mode.set(mode_label)
        dashboard._on_mode_change(None)

        self.controller.notebook.select(dashboard)

        self.controller.log(
            f"📥 Đã import {count} project → Queue  "
            f"(Mode: {mode_label} | GEM: {gem_name})",
            "SUCCESS"
        )
