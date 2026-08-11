import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

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
        "required_subdirs":  ["character"],
        "input2_folder":     "character",
        "output_folder":     "output",
        "auto_create_out":   True,
        "badges":            ["📸 character/", "📤 output/ (auto)"],
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
    "ScriptRaw ➡ Metadata": {
        "required_subdirs":  [],
        "input2_folder":     "",
        "output_folder":     "",
        "auto_create_out":   True,
        "badges":            ["📄 Script_raw/*.txt ➡ metadata.json"],
        "loop_type":         "script_metadata",
        "need_gem":          True,
        "validate_timecode": False,
    },
}


class SuffixDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt):
        self.prompt = prompt
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        lbl = ttk.Label(master, text=self.prompt, font=("Segoe UI", 9))
        lbl.pack(padx=15, pady=(15, 5), anchor="w")
        
        self.cbo = ttk.Combobox(master, values=["_storyboard_json", "_hook_json"], width=35)
        self.cbo.pack(padx=15, pady=(0, 15), fill="x")
        self.cbo.set("_storyboard_json")  # Mặc định chọn _storyboard_json
        
        return self.cbo  # Focus vào combobox

    def apply(self):
        self.result = self.cbo.get()


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

        # Shift+Click range selection
        self.folder_names_ordered: list[str] = []   # thứ tự hiển thị
        self._last_clicked_idx: int | None = None   # index cúa lần click trước

        self.selected_mode = tk.StringVar(value=list(IMPORT_MODES.keys())[0])
        self._build_ui()
        self.refresh_gem_list()
        self._on_mode_change()

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

        # Row 2: chọn GEM
        self.lbl_gem = ttk.Label(toolbar, text="GEM:", font=("Segoe UI", 9))
        self.lbl_gem.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))

        self.selected_gem = tk.StringVar()
        self.cbo_gem = ttk.Combobox(
            toolbar,
            textvariable=self.selected_gem,
            state="readonly",
            font=("Segoe UI", 9),
            width=35,
        )
        self.cbo_gem.grid(row=2, column=1, sticky="w", pady=(6, 0))

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(8, 0))

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
        
        cfg = IMPORT_MODES[self.selected_mode.get()]
        if cfg.get("need_gem"):
            self.lbl_gem.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
            self.cbo_gem.grid(row=2, column=1, sticky="w", pady=(6, 0))
        else:
            self.lbl_gem.grid_remove()
            self.cbo_gem.grid_remove()

    def refresh_gem_list(self):
        gems = config.global_settings.get("gems", [])
        gem_names = [g["name"] for g in gems]
        current = self.selected_gem.get()
        self.cbo_gem['values'] = gem_names
        if gem_names:
            if not current or current not in gem_names:
                self.cbo_gem.current(0)
            else:
                self.selected_gem.set(current)

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
        cfg = IMPORT_MODES[self.selected_mode.get()]
        suffix = ""

        # Không hiện Popup chọn hậu tố JSON nếu là mode ScriptRaw ➡ Metadata hoặc Thumbnail ➡ Image
        if cfg.get("loop_type") not in ["script_metadata", "thumbnail_image"]:
            dialog = SuffixDialog(
                self,
                "Chọn hậu tố JSON",
                "Chọn hoặc nhập hậu tố của file JSON cần quét:"
            )
            suffix = dialog.result
            if suffix is None:
                return
            suffix = suffix.strip()

        self._clear_list()
        self.lbl_status.config(text="⏳ Đang quét...", foreground="#ffb86c")
        self.update_idletasks()

        valid = self._find_valid_folders(root_path, cfg, suffix=suffix)

        if not valid:
            req = " + ".join(f"'{s}/'" for s in cfg["required_subdirs"])
            self.lbl_status.config(
                text=f"⚠️  Không tìm thấy project hợp lệ. Cần: 1 file .json, {req}",
                foreground="#ff5555")
            self.lbl_counter.config(text="")
            self.btn_add.config(state="disabled")
            return

        # Thống kê trạng thái hoàn thành
        n_done    = sum(1 for d in valid.values()
                        if d.get("tc_ok", True) and d.get("char_ok", True)
                        and len(d.get("pending", [])) == 0 and len(d.get("completed", [])) > 0)
        n_partial = sum(1 for d in valid.values()
                        if d.get("tc_ok", True) and d.get("char_ok", True)
                        and len(d.get("pending", [])) > 0 and len(d.get("completed", [])) > 0)
        n_new     = sum(1 for d in valid.values()
                        if d.get("tc_ok", True) and d.get("char_ok", True)
                        and len(d.get("completed", [])) == 0)

        parts = [f"✅ {n_done} xong"] if n_done else []
        if n_partial:
            parts.append(f"🔶 {n_partial} một phần")
        if n_new:
            parts.append(f"🆕 {n_new} chưa làm")
        summary = " | ".join(parts) if parts else ""
        status_txt = f"Tìm thấy {len(valid)} project.  {summary}" if summary else f"Tìm thấy {len(valid)} project."
        self.lbl_status.config(text=status_txt, foreground="#6cc644")

        for idx, (name, data) in enumerate(valid.items()):
            self._add_folder_row(idx, name, data, cfg)

        self.folder_data = valid
        self._update_counter()
        self.btn_add.config(state="normal")

        # Log tất cả lỗi timecode & thiếu ảnh nhân vật xuống nhật ký
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
            
            if not data.get("char_ok", True):
                char_bad_stts = data.get("char_bad_stts", [])
                if char_bad_stts:
                    chars_str = ", ".join(char_bad_stts)
                    self.controller.log(
                        f"⚠️  [{name}] Thiếu ảnh nhân vật — Tên nhân vật thiếu: {chars_str}",
                        "WARNING"
                    )


    def _find_valid_folders(self, root_path: str, cfg: dict, suffix: str = "") -> dict:
        """
        Generic scanner: hợp lệ khi tìm được file json phù hợp và tất cả required_subdirs tồn tại.
        Trả về {folder_name: {"json": path, "subdirs": {name: path}}}
        """
        result = {}

        # Xử lý riêng cho mode ScriptRaw ➡ Metadata
        if cfg.get("loop_type") == "script_metadata":
            import re
            from utils.pre_upload_ops import extract_4digit_id
            from utils.file_ops import get_script_metadata_status

            script_raw_dir = root_path
            if os.path.isdir(os.path.join(root_path, "Script_raw")):
                script_raw_dir = os.path.join(root_path, "Script_raw")

            if os.path.exists(script_raw_dir) and os.path.isdir(script_raw_dir):
                try:
                    entries = sorted(os.listdir(script_raw_dir))
                except Exception:
                    entries = []

                for txt_f in entries:
                    if not txt_f.lower().endswith(".txt"):
                        continue
                    vid_id = extract_4digit_id(txt_f) or os.path.splitext(txt_f)[0]
                    txt_path = os.path.join(script_raw_dir, txt_f)

                    base_dir = os.path.dirname(script_raw_dir) if os.path.basename(script_raw_dir) == "Script_raw" else root_path
                    if os.path.exists(os.path.join(base_dir, "0001_input")):
                        out_dir = os.path.join(base_dir, "0001_input", vid_id)
                    else:
                        out_dir = os.path.join(base_dir, vid_id)

                    pending_tasks, completed_tasks = get_script_metadata_status(txt_path, out_dir)
                    result[vid_id] = {
                        "json": txt_path,
                        "subdirs": {},
                        "root": out_dir,
                        "out": out_dir,
                        "tc_ok": True,
                        "tc_err": "",
                        "tc_bad_stts": [],
                        "char_ok": True,
                        "char_err": "",
                        "char_bad_stts": [],
                        "pending": pending_tasks,
                        "completed": completed_tasks,
                    }
            return result



        try:
            entries = sorted(
                os.listdir(root_path),
                key=lambda x: x.lower()
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
                if suffix:
                    expected_json_name = f"{name}{suffix}.json"
                    json_path = os.path.join(folder_path, expected_json_name)
                    if os.path.exists(json_path) and os.path.isfile(json_path):
                        json_files = [expected_json_name]
                    else:
                        json_files = []
                else:
                    # Tìm đúng 1 file .json (logic gốc)
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

                    # Validate character images nếu thư mục "character" được yêu cầu trong mode này
                    char_ok = True
                    char_err = ""
                    char_bad_stts = []
                    if "character" in cfg.get("required_subdirs", []):
                        from utils.validators import validate_characters
                        char_dir = found_subdirs["character"]
                        char_ok, char_err, char_bad_stts = validate_characters(json_path, char_dir)

                    # Lấy pending và completed để kiểm tra xem đã xong chưa
                    pending_tasks = []
                    completed_tasks = []
                    
                    if tc_ok and char_ok:
                        from utils.file_ops import (
                            get_prompt_image_status,
                            get_image_to_video_status,
                            get_1_image_prompt_video_status,
                            get_stretch_video_status,
                        )
                        loop_type = cfg["loop_type"]
                        out_dir = os.path.join(folder_path, cfg["output_folder"])
                        try:
                            if loop_type == "prompt_image":
                                img_dir = found_subdirs.get("character", "")
                                pending_tasks, completed_tasks = get_prompt_image_status(json_path, img_dir, out_dir)
                            elif loop_type == "image_to_video":
                                img_dir = found_subdirs.get("output_image", "")
                                pending_tasks, completed_tasks = get_image_to_video_status(json_path, img_dir, out_dir)
                            elif loop_type == "1_image_prompt_video":
                                img_dir = found_subdirs.get("character", "")
                                pending_tasks, completed_tasks = get_1_image_prompt_video_status(json_path, img_dir, out_dir)
                            elif loop_type == "stretch_video":
                                video_in_dir = found_subdirs.get("output", "")
                                pending_tasks, completed_tasks = get_stretch_video_status(json_path, video_in_dir, out_dir)
                        except Exception as e:
                            print(f"⚠️ Lỗi khi lấy trạng thái hoàn thành của {name}: {e}")

                    result[name] = {
                        "json":         json_path,
                        "subdirs":      found_subdirs,
                        "root":         folder_path,
                        "tc_ok":        tc_ok,
                        "tc_err":       tc_err,
                        "tc_bad_stts":  tc_bad_stts,
                        "char_ok":      char_ok,
                        "char_err":     char_err,
                        "char_bad_stts": char_bad_stts,
                        "pending":      pending_tasks,
                        "completed":    completed_tasks,
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
        tc_ok   = data.get("tc_ok", True)
        char_ok = data.get("char_ok", True)
        is_ok   = tc_ok and char_ok

        pending_tasks   = data.get("pending", [])
        completed_tasks = data.get("completed", [])
        n_pending   = len(pending_tasks)
        n_completed = len(completed_tasks)

        # Xác định trạng thái hoàn thành
        # is_ok=True mới có pending/completed data
        is_fully_done   = is_ok and n_pending == 0 and n_completed > 0
        is_partial_done = is_ok and n_pending > 0  and n_completed > 0

        bg = self.ROW_EVEN if idx % 2 == 0 else self.ROW_ODD

        card = tk.Frame(self.scroll_frame, bg=bg, pady=5, padx=8)
        card.pack(fill="x")
        card.bind("<MouseWheel>", self._on_mousewheel)
        # Bind mousewheel cho tất cả widget con để scroll hoạt động khi hover lên text/checkbox
        def _bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", self._on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)
        card.after(10, lambda c=card: _bind_mousewheel_recursive(c))
        card.bind("<Enter>",  lambda e, f=card: f.config(bg=self.ROW_HOVER))
        card.bind("<Leave>",  lambda e, f=card, b=bg: f.config(bg=b))

        # Checkbox
        # - disabled nếu timecode sai / thiếu ảnh
        # - disabled + uncheck nếu đã hoàn thành 100%
        default_checked = is_ok and not is_fully_done
        var = tk.BooleanVar(value=default_checked)
        self.folder_vars[name] = var
        self.folder_names_ordered.append(name)      # ghi nhớ thứ tự

        chk = ttk.Checkbutton(card, variable=var, cursor="hand2")
        if not is_ok or is_fully_done:
            chk.state(["disabled"])        # disable, không cho chọn
        else:
            # Dùng ButtonRelease-1 duy nhất — chạy after(1ms) để đọc state SAU khi Tkinter toggle
            chk.bind("<ButtonRelease-1>",
                     lambda e, n=name: self.after(1, lambda ev=e, nm=n: self._on_chk_release(ev, nm)))
        chk.pack(side="left", padx=(0, 4))

        # STT
        tk.Label(card, text=f"{idx+1:>3}.", bg=bg,
                 fg="#555", font=("Segoe UI", 9), width=3).pack(side="left", padx=(0, 6))

        # Folder name
        # - đỏ/vàng nếu lỗi
        # - xanh lá nếu done 100%
        # - cam nhạt nếu một phần
        # - trắng nếu chưa làm
        if not is_ok:
            name_color = "#ffaa00"
        elif is_fully_done:
            name_color = "#4caf50"
        elif is_partial_done:
            name_color = "#ff9800"
        else:
            name_color = "#e0e0e0"

        tk.Label(card, text=name, bg=bg,
                 fg=name_color, font=("Segoe UI", 10, "bold"),
                 width=20, anchor="w").pack(side="left", padx=(0, 12))

        # JSON filename
        json_name = os.path.basename(data["json"])
        json_disp = (json_name[:22] + "…") if len(json_name) > 24 else json_name
        tk.Label(card, text=f"📄 {json_disp}", bg=bg,
                 fg="#cccccc", font=("Consolas", 8),
                 width=26, anchor="w").pack(side="left", padx=(0, 10))

        if is_ok:
            # Badges bình thường
            for label in cfg["badges"]:
                tk.Label(card, text=label, bg=bg,
                         fg="#aaaaaa", font=("Segoe UI", 8)).pack(side="left", padx=(0, 10))

            # Badge trạng thái hoàn thành
            if is_fully_done:
                done_txt = f"✅ Đã xong ({n_completed} tasks)"
                tk.Label(card, text=done_txt, bg=bg,
                         fg="#4caf50", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
            elif is_partial_done:
                # Hiển thị tối đa 3 STT còn thiếu (pending_tasks là list dict có key "STT")
                sample = pending_tasks[:3]
                suffix = f" +{n_pending - 3} nữa" if n_pending > 3 else ""
                pending_str = ", ".join(
                    str(t["STT"]) if isinstance(t, dict) else str(t)
                    for t in sample
                ) + suffix
                partial_txt = f"🔶 Còn {n_pending} task ({pending_str})"
                tk.Label(card, text=partial_txt, bg=bg,
                         fg="#ff9800", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        else:
            # Hiển thị các lỗi (timecode, thiếu ảnh nhân vật, hoặc sai cấu trúc JSON)
            warn_txts = []
            if not tc_ok:
                bad_stts = data.get("tc_bad_stts", [])
                if bad_stts:
                    stts_str = ", ".join(bad_stts[:4])
                    suffix   = f" (+{len(bad_stts)-4} nữa)" if len(bad_stts) > 4 else ""
                    warn_txts.append(f"⚠️ STT lỗi TC: {stts_str}{suffix}")
                else:
                    tc_err = data.get("tc_err", "")
                    first_line = tc_err.splitlines()[0].strip() if tc_err else "⚠️ Timecode sai định dạng"
                    warn_txts.append(f"⚠️ {first_line}")
                    
            if not char_ok:
                char_bad_stts = data.get("char_bad_stts", [])
                if char_bad_stts:
                    chars_str = ", ".join(char_bad_stts[:4])
                    suffix   = f" (+{len(char_bad_stts)-4} nữa)" if len(char_bad_stts) > 4 else ""
                    warn_txts.append(f"⚠️ Thiếu ảnh: {chars_str}{suffix}")
                else:
                    char_err = data.get("char_err", "")
                    first_line = char_err.splitlines()[0].strip() if char_err else "⚠️ Thiếu ảnh nhân vật"
                    if not tc_ok and first_line in " ".join(warn_txts):
                        pass
                    else:
                        warn_txts.append(f"⚠️ {first_line}")
            
            warn_txt = " | ".join(warn_txts)
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
        for name, var in self.folder_vars.items():
            data = self.folder_data.get(name, {})
            is_ok = data.get("tc_ok", True) and data.get("char_ok", True)
            pending = data.get("pending", [])
            completed = data.get("completed", [])
            is_fully_done = is_ok and len(pending) == 0 and len(completed) > 0
            if is_ok and not is_fully_done:
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
        self.folder_names_ordered.clear()
        self._last_clicked_idx = None
        self.lbl_counter.config(text="")
        self.btn_add.config(state="disabled")

    def _on_chk_release(self, event, name: str):
        """
        Xử lý sau khi Tkinter đã toggle var (sau 1ms).
        Nếu Shift được giữ (event.state & 0x1) → chọn range.
        Nếu không → ghi nhớ index và update counter.
        """
        is_shift = bool(event.state & 0x1)

        if is_shift and self._last_clicked_idx is not None and name in self.folder_names_ordered:
            cur_idx   = self.folder_names_ordered.index(name)
            start     = min(self._last_clicked_idx, cur_idx)
            end       = max(self._last_clicked_idx, cur_idx)
            new_state = self.folder_vars[name].get()   # được toggle xong rồi

            for i in range(start, end + 1):
                n   = self.folder_names_ordered[i]
                var = self.folder_vars.get(n)
                if var is None:
                    continue
                data          = self.folder_data.get(n, {})
                is_ok         = data.get("tc_ok", True) and data.get("char_ok", True)
                n_pending     = len(data.get("pending", []))
                n_completed   = len(data.get("completed", []))
                is_fully_done = is_ok and n_pending == 0 and n_completed > 0
                if is_ok and not is_fully_done:
                    var.set(new_state)

            self._last_clicked_idx = cur_idx
        else:
            # Click thường — ghi nhớ index
            if name in self.folder_names_ordered:
                self._last_clicked_idx = self.folder_names_ordered.index(name)

        self._update_counter()

    # ─── giữ lại các method cũ để tương thích (không dùng nữa nhưng không xóa)
    def _on_click(self, name: str):
        if name in self.folder_names_ordered:
            self._last_clicked_idx = self.folder_names_ordered.index(name)
        self._update_counter()

    def _on_shift_click(self, name: str):
        pass   # deprecated — thay thế bởi _on_chk_release

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
            selected_gem_name = self.selected_gem.get()
            gems = config.global_settings.get("gems", [])
            gem = next((g for g in gems if g["name"] == selected_gem_name), None)
            if not gem:
                messagebox.showwarning(
                    "Thiếu GEM",
                    "Vui lòng chọn GEM hợp lệ!")
                return
            gem_name = gem["name"]
            url      = gem.get("url", "")
        else:
            gem_name = "Local FFmpeg"         # Stretch mode: FFmpeg local

        # ── Add từng project ─────────────────────
        dashboard = self.controller.tab_dashboard
        count = 0
        skipped_done = []   # project đã hoàn thành 100%

        for name in selected:
            if name not in self.folder_data:
                continue
            data = self.folder_data[name]

            # Bỏ qua nếu timecode sai hoặc thiếu ảnh nhân vật (checkbox đã disabled nhưng guard chắc chắn)
            if not data.get("tc_ok", True) or not data.get("char_ok", True):
                continue

            # Bỏ qua nếu project đã hoàn thành 100%
            pending_tasks   = data.get("pending", [])
            completed_tasks = data.get("completed", [])
            if len(pending_tasks) == 0 and len(completed_tasks) > 0:
                skipped_done.append(name)
                continue

            # input2: folder nguồn (character/ hoặc output/)
            inp2 = data["subdirs"].get(cfg["input2_folder"], "")

            # output: folder đích (output/ hoặc final/ hoặc data["out"])
            out = data.get("out") or (os.path.join(data["root"], cfg["output_folder"]) if cfg["output_folder"] else data["root"])

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

        # Log các project đã bỏ qua vì hoàn thành 100%
        if skipped_done:
            for done_name in skipped_done:
                n_done = len(self.folder_data[done_name].get("completed", []))
                self.controller.log(
                    f"✅ [{done_name}] Đã hoàn thành ({n_done} tasks) — Bỏ qua.",
                    "INFO"
                )


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
