import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os

from config import DEFAULT_INPUT, DEFAULT_OUTPUT, load_config, global_settings

SETTINGS_FILE = "settings.json"

class DashboardTab(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller 
        self.project_queue = []
        
        self.lang_vars = {}
        self.gem_vars = {}
        
        self.settings = global_settings
        self.lang_objects = self.settings.get("standardize", {}).get("languages", [])
        self.gems_data = self.settings.get("gems", [])
        
        # Gọi hàm setup giao diện đã được chia nhỏ
        self._setup_ui()
        self._load_defaults() 
        self._on_mode_change(None)

    # ==========================================
    # PHẦN 1: QUẢN LÝ VẼ GIAO DIỆN (UI BUILDERS)
    # ==========================================
    def _setup_ui(self):
        """Khởi tạo toàn bộ UI bằng cách gọi các block nhỏ"""
        self._build_top_controls()
        self._build_dynamic_options()
        self._build_add_project_form()
        self._build_dashboard_stats()
        self._build_queue_treeview()

    def _build_top_controls(self):
        """Khối 1: Chọn chế độ và nút Run/Stop"""
        self.frame_ctrl = ttk.Frame(self, padding=10)
        self.frame_ctrl.pack(fill="x")
        
        tk.Label(self.frame_ctrl, text="Chế độ chạy:", fg="white", bg="#2b2b2b").pack(side="left", padx=5)
        
        self.selected_mode = tk.StringVar(value="Image ➡ Prompt")
        self.cbo_mode = ttk.Combobox(self.frame_ctrl, textvariable=self.selected_mode, state="readonly", width=25)
        self.cbo_mode['values'] = (
            "SRT ➡ Prompt", 
            "Prompt ➡ Image", 
            "Image + Prompt ➡ Video",
            "Video ➡ Stretch (Timecode)"
        )
        self.cbo_mode.pack(side="left", padx=5)
        self.cbo_mode.bind("<<ComboboxSelected>>", self._on_mode_change)

        self.btn_run = ttk.Button(self.frame_ctrl, text="▶ CHẠY LIST", style="Accent.TButton", command=self.controller.on_start_batch)
        self.btn_run.pack(side="left", padx=20)
        
        self.btn_stop = ttk.Button(self.frame_ctrl, text="🛑 DỪNG", command=self.controller.stop_process, state="disabled")
        self.btn_stop.pack(side="right")

    def _build_dynamic_options(self):
        pass
            
    def _build_add_project_form(self):
        """Khối 3: Thêm Input/Output/GEM"""
        frame_add = ttk.LabelFrame(self, text="➕ Thêm Dự án", padding=10)
        frame_add.pack(fill="x", padx=10, pady=5)
        frame_add.columnconfigure(1, weight=1)
        
        # Input
        self.lbl_in = tk.Label(frame_add, text="Input:", fg="white", bg="#2b2b2b")
        self.lbl_in.grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.entry_in = ttk.Entry(frame_add)
        self.entry_in.insert(0, DEFAULT_INPUT)
        self.entry_in.grid(row=0, column=1, sticky="ew", padx=5)
        self.btn_in = ttk.Button(frame_add, text="📂", width=3, command=self._pick_input)
        self.btn_in.grid(row=0, column=2, padx=5)

        # Input 2 (Image Folder)
        self.lbl_in2 = tk.Label(frame_add, text="Folder Ảnh:", fg="white", bg="#2b2b2b")
        self.entry_in2 = ttk.Entry(frame_add)
        self.entry_in2.insert(0, DEFAULT_INPUT)
        self.btn_in2 = ttk.Button(frame_add, text="📂", width=3, command=lambda: self._pick_folder(self.entry_in2))

        # Output
        self.lbl_out = tk.Label(frame_add, text="Output:", fg="white", bg="#2b2b2b")
        self.lbl_out.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.entry_out = ttk.Entry(frame_add)
        self.entry_out.insert(0, DEFAULT_OUTPUT)
        self.entry_out.grid(row=2, column=1, sticky="ew", padx=5)
        self.btn_out = ttk.Button(frame_add, text="📂", width=3, command=lambda: self._pick_folder(self.entry_out))
        self.btn_out.grid(row=2, column=2, padx=5)

        # GEM & Prompt
        tk.Label(frame_add, text="GEM:", fg="white", bg="#2b2b2b").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        frame_url_prompt = ttk.Frame(frame_add)
        frame_url_prompt.grid(row=3, column=1, columnspan=2, sticky="ew", pady=5)
        frame_url_prompt.columnconfigure(0, weight=1)
        frame_url_prompt.columnconfigure(1, weight=2)

        gem_names = [g["name"] for g in self.gems_data]
        self.cbo_gem_url = ttk.Combobox(frame_url_prompt, values=gem_names, state="readonly")
        if gem_names: self.cbo_gem_url.current(0)
        self.cbo_gem_url.grid(row=0, column=0, sticky="ew", padx=(5, 5))
        
        self.entry_prompt = ttk.Entry(frame_url_prompt)
        self.entry_prompt.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self._set_placeholder(self.entry_prompt, "Nhập Prompt (Tùy chọn)...")

        self.btn_add = ttk.Button(frame_add, text="⬇ THÊM", command=self.add_project_to_queue)
        self.btn_add.grid(row=0, column=3, rowspan=4, padx=10, sticky="ns")

    def _build_dashboard_stats(self):
        """Khối 4: Hiển thị thống kê số lượng task"""
        frame_dash = ttk.LabelFrame(self, text="📊 Tiến độ Real-time", padding=15)
        frame_dash.pack(fill="x", padx=10, pady=5)
        for i in range(3): frame_dash.columnconfigure(i, weight=1)

        def create_stat_box(parent, col, title, color):
            f = ttk.Frame(parent)
            f.grid(row=0, column=col)
            lbl = ttk.Label(f, text="0", font=("Segoe UI", 24, "bold"), foreground=color)
            lbl.pack()
            ttk.Label(f, text=title).pack()
            return lbl

        self.lbl_total = create_stat_box(frame_dash, 0, "TỔNG", "#888888")
        self.lbl_pending = create_stat_box(frame_dash, 1, "CẦN LÀM", "#ffaa00")
        self.lbl_done = create_stat_box(frame_dash, 2, "ĐÃ XONG", "#00cc6a")
        # Chỉnh font riêng cho Pending to hơn
        self.lbl_pending.config(font=("Segoe UI", 32, "bold"))

    def _build_queue_treeview(self):
        """Khối 5: Bảng danh sách hàng chờ"""
        frame_list = ttk.LabelFrame(self, text="📋 Hàng chờ", padding=10)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        # Action bar (nút Xóa) — pack trước để không bị đẩy khi scroll
        frame_act = ttk.Frame(frame_list)
        frame_act.pack(side="bottom", fill="x", pady=5)
        ttk.Button(frame_act, text="❌ Xóa", command=self.remove_selected_project).pack(side="right")
        ttk.Button(frame_act, text="🧹 Xóa hết", command=self.clear_all_projects).pack(side="right", padx=5)

        # Container cho tree + 2 scrollbar
        tree_container = ttk.Frame(frame_list)
        tree_container.pack(fill="both", expand=True)

        columns = ("stt", "input", "output", "gem", "prompt", "status")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", height=6)

        titles = {"stt": "#", "input": "Input", "output": "Output", "gem": "GEM", "prompt": "Prompt", "status": "Trạng thái"}
        widths = {"stt": 35, "input": 200, "output": 200, "gem": 80, "prompt": 150, "status": 280}
        for col, txt in titles.items():
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=widths[col], minwidth=widths[col],
                             stretch=False,
                             anchor="center" if col in ["stt", "status"] else "w")

        # Vertical scrollbar
        sb_y = ttk.Scrollbar(tree_container, orient="vertical",   command=self.tree.yview)
        # Horizontal scrollbar
        sb_x = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)

        self.tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        sb_y.pack(side="right",  fill="y")
        sb_x.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)


    # ==========================================
    # PHẦN 2: XỬ LÝ LOGIC SỰ KIỆN (EVENT HANDLERS)
    # ==========================================
    def _on_mode_change(self, event):
        mode = self.selected_mode.get()
            
        if mode in ["Prompt ➡ Image", "Image + Prompt ➡ Video", "Video ➡ Stretch (Timecode)"]:
            self.lbl_in.config(text="File JSON Prompt:")
            if mode == "Video ➡ Stretch (Timecode)":
                self.lbl_in2.configure(text="Thư mục Video Gốc:")
            else:
                self.lbl_in2.configure(text="Thư mục Ảnh:")
            self.lbl_in2.grid(row=1, column=0, sticky="w", padx=5, pady=5)
            self.entry_in2.grid(row=1, column=1, sticky="ew", padx=5)
            self.btn_in2.grid(row=1, column=2, padx=5)
        else:
            self.lbl_in.config(text="Input:")
            self.lbl_in2.grid_forget()
            self.entry_in2.grid_forget()
            self.btn_in2.grid_forget()

    def _pick_input(self):
        mode = self.selected_mode.get()
        file_modes = ["SRT ➡ Prompt", "Prompt ➡ Image", "Image + Prompt ➡ Video", "Video ➡ Stretch (Timecode)"]
        
        if mode in file_modes:
            if "SRT" in mode:
                f = filedialog.askopenfilename(title="Chọn file SRT", filetypes=[("SRT Files", "*.srt")])
            else:
                f = filedialog.askopenfilename(title="Chọn file JSON", filetypes=[("JSON", "*.json")])
        else:
            f = filedialog.askdirectory(title="Chọn thư mục Input")
            
        if f:
            self.entry_in.delete(0, tk.END)
            self.entry_in.insert(0, f)

    def add_project_to_queue(self):
        inp = self.entry_in.get().strip()
        out = self.entry_out.get().strip()
        inp2 = self.entry_in2.get().strip() if self.entry_in2.winfo_ismapped() else ""
        gem_name = self.cbo_gem_url.get().strip()
        prompt_val = self.entry_prompt.get().strip()
        mode = self.selected_mode.get()

        if prompt_val == "Nhập Prompt (Tùy chọn)...": prompt_val = ""
        if not inp or not out or not gem_name:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ Input, Output và chọn GEM!")
            return
            
        if mode in ["Prompt ➡ Image", "Image + Prompt ➡ Video", "Video ➡ Stretch (Timecode)"]:
            if not inp or not os.path.isfile(inp):
                messagebox.showerror("Lỗi", "Vui lòng chọn File JSON.")
                return
            if not inp2 or not os.path.isdir(inp2):
                messagebox.showerror("Lỗi", "Vui lòng chọn Thư mục Input 2 (Ảnh/Video).")
                return

        real_url = next((g["url"] for g in self.gems_data if g["name"] == gem_name), "https://gemini.google.com")

        self.project_queue.append({
            "input": inp, "input2": inp2, "output": out, "url": real_url, "gem_name": gem_name,
            "prompt": prompt_val, "languages": [], 
            "shuffle_gems": [], "status": "Waiting"
        })
        self.refresh_treeview()

    # ==========================================
    # PHẦN 3: CÁC HÀM TIỆN ÍCH (UTILITIES)
    # ==========================================
    def _set_placeholder(self, entry, text):
        entry.insert(0, text); entry.config(foreground="grey")
        entry.bind("<FocusIn>", lambda e: self._clear_placeholder(e, text))
        entry.bind("<FocusOut>", lambda e: self._add_placeholder(e, text))

    def _clear_placeholder(self, event, text):
        if event.widget.get() == text:
            event.widget.delete(0, tk.END); event.widget.config(foreground="white")

    def _add_placeholder(self, event, text):
        if not event.widget.get():
            event.widget.insert(0, text); event.widget.config(foreground="grey")

    def _pick_folder(self, entry):
        d = filedialog.askdirectory()
        if d: entry.delete(0, tk.END); entry.insert(0, d)

    def remove_selected_project(self):
        sel = self.tree.selection()
        if sel:
            for item in reversed(sel):
                del self.project_queue[self.tree.index(item)]
            self.refresh_treeview()

    def clear_all_projects(self):
        self.project_queue.clear()
        self.refresh_treeview()

    def add_project_direct(self, inp, inp2, out, url, gem_name, prompt=""):
        """
        Thêm project vào queue theo cách lập trình (không qua form UI).
        Dùng bởi ImportProjectTab để bulk-import nhiều project cùng lúc.
        """
        self.project_queue.append({
            "input":       inp,
            "input2":      inp2,
            "output":      out,
            "url":         url,
            "gem_name":    gem_name,
            "prompt":      prompt,
            "languages":   [],
            "shuffle_gems": [],
            "status":      "Waiting"
        })
        self.refresh_treeview()

    def refresh_treeview(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for i, p in enumerate(self.project_queue):
            input_disp = f"{p['input']} | ẢNH: {p['input2']}" if p.get('input2') else p["input"]
            self.tree.insert("", "end", values=(i+1, input_disp, p["output"], p["gem_name"], p["prompt"], p["status"]))

    def _load_defaults(self):
        pass

    def refresh_gem_list(self):
        self.gems_data = self.settings.get("gems", [])
        gem_names = [g["name"] for g in self.gems_data]
        if hasattr(self, 'cbo_gem_url'):
            current = self.cbo_gem_url.get()
            self.cbo_gem_url['values'] = gem_names
            if gem_names and (not current or current not in gem_names):
                self.cbo_gem_url.current(0)

    def update_project_status(self, index, status):
        if 0 <= index < len(self.project_queue):
            self.project_queue[index]["status"] = status
            try:
                self.tree.set(self.tree.get_children()[index], "status", status)
            except: pass

    def update_dashboard_stats(self, total, pending, done):
        self.lbl_total.config(text=f"{total}")
        self.lbl_pending.config(text=f"{pending}")
        self.lbl_done.config(text=f"{done}")

    def toggle_buttons(self, is_running):
        self.btn_run.config(state="disabled" if is_running else "normal")
        self.btn_stop.config(state="normal" if is_running else "disabled")
        self.cbo_mode.config(state="disabled" if is_running else "readonly")