import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import config  # <--- IMPORT MODULE CẤU HÌNH (QUAN TRỌNG)

class SettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        # Load trực tiếp từ biến toàn cục trong RAM
        self.settings = config.global_settings
        self._setup_ui()

    def _setup_ui(self):
        # Chia layout thành 2 phần: Trái (Cấu hình) - Phải (Quản lý)
        # Sử dụng PanedWindow
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # --- PHẦN TRÁI: CẤU HÌNH HỆ THỐNG (SIDEBAR) ---
        left_frame = ttk.LabelFrame(paned, text="⚙️ Cấu hình Hệ thống", padding=10)
        paned.add(left_frame, weight=1) 

        # Dàn các control theo chiều dọc (Grid layout)
        
        # 1. Threads
        tk.Label(left_frame, text="Max Threads:", anchor="w").grid(row=0, column=0, sticky="w", pady=(10, 5))
        self.var_threads = tk.IntVar(value=self.settings["system"].get("max_threads", 3))
        ttk.Spinbox(left_frame, from_=1, to=20, textvariable=self.var_threads, width=15).grid(row=1, column=0, sticky="ew")

        # 2. Batch Loop
        tk.Label(left_frame, text="Loop Limit (Batch):", anchor="w").grid(row=2, column=0, sticky="w", pady=(15, 5))
        self.var_limit = tk.IntVar(value=self.settings["system"].get("loop_limit", 5))
        ttk.Spinbox(left_frame, from_=1, to=100, textvariable=self.var_limit, width=15).grid(row=3, column=0, sticky="ew")

        # 3. Retries
        tk.Label(left_frame, text="Max Retries:", anchor="w").grid(row=4, column=0, sticky="w", pady=(15, 5))
        self.var_retries = tk.IntVar(value=self.settings["system"].get("max_retries", 30))
        ttk.Entry(left_frame, textvariable=self.var_retries, width=15).grid(row=5, column=0, sticky="ew")

        # 4. Wait Time
        tk.Label(left_frame, text="Wait Time (s):", anchor="w").grid(row=6, column=0, sticky="w", pady=(15, 5))
        self.var_wait_time = tk.IntVar(value=self.settings["system"].get("wait_time", 5))
        ttk.Spinbox(left_frame, from_=1, to=60, textvariable=self.var_wait_time, width=15).grid(row=7, column=0, sticky="ew")

        # 5. Aspect Ratio (Grok Video)
        tk.Label(left_frame, text="Aspect Ratio (Grok):", anchor="w").grid(row=8, column=0, sticky="w", pady=(15, 5))
        self.var_aspect_ratio = tk.StringVar(value=self.settings["system"].get("aspect_ratio", "16:9"))
        cb_ar = ttk.Combobox(left_frame, textvariable=self.var_aspect_ratio, values=["16:9", "9:16", "1:1"], state="readonly", width=13)
        cb_ar.grid(row=9, column=0, sticky="ew")

        # 6. Resolution (Grok Video)
        tk.Label(left_frame, text="Resolution (Grok):", anchor="w").grid(row=10, column=0, sticky="w", pady=(15, 5))
        self.var_resolution = tk.StringVar(value=self.settings["system"].get("resolution", "720p"))
        cb_res = ttk.Combobox(left_frame, textvariable=self.var_resolution, values=["720p", "1080p", "480p"], state="readonly", width=13)
        cb_res.grid(row=11, column=0, sticky="ew")

        # Nút Save nằm dưới cùng, giãn cách xa một chút
        ttk.Separator(left_frame, orient='horizontal').grid(row=12, column=0, sticky="ew", pady=20)
        
        ttk.Button(left_frame, text="💾 LƯU CẤU HÌNH", style="Accent.TButton", command=self.save_settings).grid(row=13, column=0, sticky="ew", pady=5)
        ttk.Button(left_frame, text="🔄 Mặc định", command=self.reset_defaults).grid(row=14, column=0, sticky="ew")

        left_frame.columnconfigure(0, weight=1) # Để các input giãn full bề ngang cột trái


        # --- PHẦN PHẢI: QUẢN LÝ DỰ ÁN & GEM (CONTENT) ---
        right_main_frame = ttk.Frame(paned)
        paned.add(right_main_frame, weight=4) # Chiếm phần lớn diện tích

        # 1. Khối Quản lý Dự án
        project_frame = ttk.LabelFrame(right_main_frame, text="📁 Quản lý Dự án", padding=10)
        project_frame.pack(fill="x", pady=(0, 15))

        # Dòng 1: Label + Combobox + Button
        p_row1 = ttk.Frame(project_frame)
        p_row1.pack(fill="x")
        
        ttk.Label(p_row1, text="Danh sách dự án:").pack(side="left")
        self.cbo_projects_preview = ttk.Combobox(p_row1, state="readonly", height=10)
        self.cbo_projects_preview.pack(side="left", fill="x", expand=True, padx=10)
        
        ttk.Button(p_row1, text="✨ Tạo Mới", command=self.open_create_project_popup).pack(side="right")
        
        self._refresh_project_combobox()

        # 2. Khối Quản lý GEM
        gem_frame = ttk.LabelFrame(right_main_frame, text="💎 Quản lý GEM", padding=10)
        gem_frame.pack(fill="both", expand=True)

        # A. Input Row
        input_row = ttk.Frame(gem_frame)
        input_row.pack(fill="x", pady=(0, 10))

        self.entry_name = ttk.Entry(input_row, width=20)
        self.entry_name.pack(side="left", padx=(0, 5))
        self._set_placeholder(self.entry_name, "Tên Gem...")

        self.entry_url = ttk.Entry(input_row)
        self.entry_url.pack(side="left", fill="x", expand=True, padx=5)
        self._set_placeholder(self.entry_url, "URL...")

        self.entry_description = ttk.Entry(input_row)
        self.entry_description.pack(side="left", fill="x", expand=True, padx=5)
        self._set_placeholder(self.entry_description, "Mô tả...")

        ttk.Button(input_row, text="➕ Thêm", command=self.add_gem).pack(side="left", padx=5)

        # B. Treeview
        tree_container = ttk.Frame(gem_frame)
        tree_container.pack(fill="both", expand=True)

        self.gem_tree = ttk.Treeview(tree_container, columns=("name", "url", "description"), show="headings", selectmode="browse")
        self.gem_tree.heading("name", text="Tên Gem")
        self.gem_tree.heading("url", text="URL")
        self.gem_tree.heading("description", text="Mô tả")
        self.gem_tree.column("name", width=150, minwidth=100, stretch=False)
        self.gem_tree.column("url", width=300, minwidth=200, stretch=True)
        self.gem_tree.column("description", width=300, minwidth=200, stretch=True)

        sb_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.gem_tree.yview)
        self.gem_tree.configure(yscrollcommand=sb_y.set)
        
        self.gem_tree.pack(side="left", fill="both", expand=True)
        sb_y.pack(side="right", fill="y")

        # C. Action Bar
        action_bar = ttk.Frame(gem_frame)
        action_bar.pack(fill="x", pady=(5, 0))
        ttk.Label(action_bar, text="* Mẹo: Double click để copy URL", font=("Arial", 8), foreground="gray").pack(side="left")
        ttk.Button(action_bar, text="🗑️ Xóa dòng chọn", command=self.delete_gem).pack(side="right")

        self._load_gems_to_tree()

    # --- LOGIC XỬ LÝ ---

    def _refresh_project_combobox(self):
        # Lấy từ config global
        project_names = [p["name"] for p in config.global_settings.get("projects", [])]
        self.cbo_projects_preview['values'] = project_names
        if project_names:
            self.cbo_projects_preview.current(len(project_names)-1)

    def open_create_project_popup(self):
        popup = tk.Toplevel(self)
        popup.title("Khởi tạo Dự án Mới")
        popup.geometry("500x220")
        popup.resizable(False, False)
        
        try:
            popup.transient(self.winfo_toplevel())
            popup.grab_set()
        except: pass

        content = ttk.Frame(popup, padding=20)
        content.pack(fill="both", expand=True)

        # UI Tạo dự án
        ttk.Label(content, text="Tên Dự án:").grid(row=0, column=0, sticky="w", pady=5)
        name_var = tk.StringVar()
        ttk.Entry(content, textvariable=name_var, width=40).grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        ttk.Label(content, text="Nơi lưu:").grid(row=1, column=0, sticky="w", pady=5)
        path_var = tk.StringVar()
        ttk.Entry(content, textvariable=path_var, width=30).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        def browse():
            d = filedialog.askdirectory()
            if d: path_var.set(d)
        ttk.Button(content, text="📂", width=3, command=browse).grid(row=1, column=2, pady=5)
        
        ttk.Label(content, text="(Để trống = tự tạo trong folder 'assets')", font=("Arial", 8, "italic"), foreground="gray").grid(row=2, column=1, sticky="w", padx=5)

        def save_action():
            p_name = name_var.get().strip()
            p_path = path_var.get().strip()
            if not p_name:
                messagebox.showerror("Lỗi", "Nhập tên dự án!", parent=popup); return
            
            if not p_path:
                p_path = os.path.join(os.getcwd(), 'assets', p_name)

            # Tạo folder
            try:
                folders = [
                    "input", "output", "init_assesst", "voice_process",
                    "process/image_and_prompt_to_video/2_image_and_prompt_to_video",
                    "process/image_and_prompt_to_video/1_image_and_prompt_to_video",
                    "process/image_to_prompt/2_image_to_prompt",
                    "process/image_to_prompt/1_image_to_prompt",
                    "process/srt_to_image",
                    "process/srt_to_prompt/prompt_to_image"
                ]
                for f in folders:
                    os.makedirs(os.path.join(p_path, *f.split("/")), exist_ok=True)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không tạo được folder: {e}", parent=popup); return

            # Check trùng trong global config
            current_projects = config.global_settings.get("projects", [])
            for p in current_projects:
                if p["name"] == p_name:
                    messagebox.showwarning("Trùng tên", "Dự án đã tồn tại.", parent=popup)
                    return

            # Thêm mới và Lưu
            config.global_settings["projects"].append({"name": p_name, "path": p_path})
            config.save_config() # Lưu ngay
            
            self._refresh_project_combobox()
            messagebox.showinfo("Thành công", f"Đã tạo: {p_name}", parent=self)
            popup.destroy()

        btn_box = ttk.Frame(content)
        btn_box.grid(row=3, column=0, columnspan=3, pady=20)
        ttk.Button(btn_box, text="Hủy", command=popup.destroy).pack(side="left", padx=10)
        ttk.Button(btn_box, text="✅ TẠO DỰ ÁN", style="Accent.TButton", command=save_action).pack(side="left", padx=10)

    # --- GEM LOGIC ---
    def _set_placeholder(self, entry, text):
        entry.insert(0, text); entry.config(foreground="grey")
        entry.bind("<FocusIn>", lambda e: self._focus_in(entry, text))
        entry.bind("<FocusOut>", lambda e: self._focus_out(entry, text))

    def _focus_in(self, entry, text):
        if entry.get() == text: entry.delete(0, tk.END); entry.config(foreground="white")

    def _focus_out(self, entry, text):
        if not entry.get(): entry.insert(0, text); entry.config(foreground="grey")

    def _load_gems_to_tree(self):
        for i in self.gem_tree.get_children(): self.gem_tree.delete(i)
        for g in config.global_settings.get("gems", []): 
            self.gem_tree.insert("", "end", values=(g["name"], g["url"], g["description"]))

    def add_gem(self):
        n, u, d = self.entry_name.get().strip(), self.entry_url.get().strip(), self.entry_description.get().strip()
        if not n or not u or n == "Tên Gem..." or u == "URL...": return
        
        config.global_settings["gems"].append({"name": n, "url": u, "description": d})
        config.save_config() # Lưu ngay
        
        self._load_gems_to_tree()
        self.entry_name.delete(0, tk.END); self._focus_out(self.entry_name, "Tên Gem...")
        self.entry_url.delete(0, tk.END); self._focus_out(self.entry_url, "URL...")
        self.entry_description.delete(0, tk.END); self._focus_out(self.entry_description, "Mô tả...")

    def delete_gem(self):
        sel = self.gem_tree.selection()
        if sel:
            idx = self.gem_tree.index(sel[0])
            del config.global_settings["gems"][idx]
            config.save_config() # Lưu ngay
            self._load_gems_to_tree()

    # --- SAVE/LOAD ---
    def save_settings(self):
        # Cập nhật giá trị từ UI vào biến Global
        config.global_settings["system"]["max_threads"] = self.var_threads.get()
        config.global_settings["system"]["loop_limit"] = self.var_limit.get()
        config.global_settings["system"]["max_retries"] = int(self.var_retries.get())
        config.global_settings["system"]["wait_time"] = self.var_wait_time.get()
        config.global_settings["system"]["aspect_ratio"] = self.var_aspect_ratio.get()
        config.global_settings["system"]["resolution"] = self.var_resolution.get()

        if config.save_config():
            messagebox.showinfo("Thành công", "Đã lưu cấu hình!")
        else:
            messagebox.showerror("Lỗi", "Không thể lưu file config!")

    def reset_defaults(self):
        if messagebox.askyesno("Xác nhận", "Về mặc định? (Dữ liệu Gem và Project sẽ mất nếu chưa lưu)"):
            # Load lại từ hàm load_config (nó sẽ reset nếu ta xóa file hoặc ta gán thủ công)
            # Ở đây ta gán thủ công từ DEFAULT_CONFIG_DATA copy
            import json
            config.global_settings.clear()
            config.global_settings.update(json.loads(json.dumps(config.DEFAULT_CONFIG_DATA)))
            
            # Refresh UI
            self.var_threads.set(config.global_settings["system"]["max_threads"])
            self.var_limit.set(config.global_settings["system"]["loop_limit"])
            self.var_retries.set(config.global_settings["system"]["max_retries"])
            self.var_wait_time.set(config.global_settings["system"]["wait_time"])
            self.var_aspect_ratio.set(config.global_settings["system"].get("aspect_ratio", "16:9"))
            self.var_resolution.set(config.global_settings["system"].get("resolution", "720p"))
            self._load_gems_to_tree()
            self._refresh_project_combobox()
            config.save_config()