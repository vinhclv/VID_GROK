import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
import threading
import time
import json
import config

import asyncio
from engine.browser_ix  import init_driver_from_profile_playwright
from utils.profile_state import ProfileStateManager

class ProfileManagerTab(ttk.Frame):
    def __init__(self, parent, profiles_dir, kill_callback=None):
        super().__init__(parent)
        self.profiles_dir = profiles_dir
        self.kill_callback = kill_callback  # fn(profile_name)
        
        # Ensure profiles directory exists
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir)
            
        # Dictionary to store Checkbox variables for each profile
        # Key: Profile Name, Value: tk.BooleanVar
        self.profile_vars = {} 
        self.card_widgets = {}  # Lưu trữ các widget của mỗi card để cập nhật trạng thái

        self.current_page = 1
        self.page_size = 20

        self.setup_ui()
        self.refresh_list()
        
        # Khởi chạy cập nhật trạng thái thời gian thực
        self.poll_status()

    def poll_status(self):
        """Cơ chế polling cập nhật trạng thái UI định kỳ"""
        if self.winfo_exists():
            self.update_ui_states()
            self.after(1000, self.poll_status)

    def update_ui_states(self):
        """Cập nhật giao diện của các profile card theo trạng thái thực tế từ ProfileStateManager"""
        states = ProfileStateManager().get_all_states()
        
        for p_name, widgets in self.card_widgets.items():
            state_info = states.get(p_name, {"status": "idle", "error_count": 0})
            status = state_info.get("status", "idle")
            err_count = state_info.get("error_count", 0)

            # Xác định nhãn hiển thị và màu sắc
            if status == "idle":
                status_text = "Rảnh rỗi (Idle)"
                status_fg = "#00cc6a" # Xanh lá
            elif status == "in_setup":
                status_text = "Đang Setup thủ công"
                status_fg = "#ffaa00" # Vàng
            elif status == "in_batch":
                if err_count > 0:
                    status_text = f"Đang chạy Batch (Lỗi: {err_count})"
                else:
                    status_text = "Đang chạy Batch"
                status_fg = "#00d4ff" # Xanh dương
            elif status == "killed":
                status_text = "Đã dừng (Killed)"
                status_fg = "#ff5555" # Đỏ sẫm
            elif status == "rate_limited":
                until = state_info.get("rate_limit_until", 0.0)
                remaining = max(0, int(until - time.time()))
                if remaining > 0:
                    mins = remaining // 60
                    secs = remaining % 60
                    status_text = f"Rate Limited (Chờ {mins}m {secs}s)"
                else:
                    status_text = "Rảnh rỗi (Idle)"
                status_fg = "#ff9900" # Cam
            elif status == "error":
                last_err = state_info.get("last_error", "")
                if "Rate Limit" in str(last_err):
                    status_text = "Lỗi (Max Rate Limit)"
                else:
                    status_text = f"Lỗi (Fails: {err_count})"
                status_fg = "#ff3333" # Đỏ tươi
            else:
                status_text = status.capitalize()
                status_fg = "#cccccc"

            # Cập nhật nhãn trạng thái
            try:
                widgets["lbl_status"].config(text=status_text, foreground=status_fg)
            except Exception:
                pass

            # Bật/Tắt các nút bấm tương ứng
            if status in ["in_setup", "in_batch"]:
                try: widgets["chk"].config(state="disabled")
                except: pass
                try: widgets["btn_setup"].config(state="disabled")
                except: pass
                
                browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
                if browser_type == "ixBrowser (Local API)":
                    try: widgets["btn_del"].config(state="normal") # Nút ❌ (đóng) luôn khả dụng
                    except: pass
                else:
                    try: widgets["btn_del"].config(state="disabled")
                    except: pass

                if widgets.get("entry_proxy"):
                    try: widgets["entry_proxy"].config(state="disabled")
                    except: pass
                
                # Chỉ mở nút ☠️ Kill nếu đang chạy batch
                if status == "in_batch":
                    try: widgets["btn_kill"].config(state="normal", text="☠️")
                    except: pass
                else:
                    try: widgets["btn_kill"].config(state="disabled")
                    except: pass
            else:
                # Profile rảnh rỗi, có lỗi, hoặc rate_limited
                try: widgets["chk"].config(state="normal")
                except: pass
                try: widgets["btn_setup"].config(state="normal")
                except: pass
                browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
                if browser_type == "ixBrowser (Local API)":
                    try: widgets["btn_del"].config(state="normal") # Nút ❌ (đóng) luôn khả dụng
                    except: pass
                else:
                    try: widgets["btn_del"].config(state="normal")
                    except: pass
                try: widgets["btn_kill"].config(state="disabled", text="☠️")
                except: pass
                if widgets.get("entry_proxy"):
                    try: widgets["entry_proxy"].config(state="normal")
                    except: pass
                try: widgets["lbl_name"].config(foreground="white")
                except: pass

    # -------------------------------------------------------
    # Proxy Map helpers
    # -------------------------------------------------------
    def import_proxy_list(self):
        """Import file .txt chứa danh sách proxy, gán xoay vòng vào profiles"""
        filepath = filedialog.askopenfilename(
            title="Chon file proxy (.txt)",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
        except Exception as e:
            messagebox.showerror("Loi", f"Khong doc duoc file: {e}")
            return

        proxies = [line.strip() for line in lines if line.strip()]
        if not proxies:
            messagebox.showwarning("Canh bao", "File khong co proxy nao hop le!")
            return

        if not os.path.exists(self.profiles_dir):
            messagebox.showwarning("Canh bao", "Chua co profile nao!")
            return

        profiles = sorted([
            f for f in os.listdir(self.profiles_dir)
            if os.path.isdir(os.path.join(self.profiles_dir, f))
        ])

        if not profiles:
            messagebox.showwarning("Canh bao", "Chua co profile nao!")
            return

        # Gan proxy xoay vong: profiles[i] <- proxies[i % len(proxies)]
        proxy_map = {}
        for i, profile in enumerate(profiles):
            proxy_map[profile] = proxies[i % len(proxies)]

        ProfileStateManager().set_proxies(proxy_map)
        self.refresh_list()

    def setup_ui(self):
        # === 1. TOOLBAR (TOP BAR) ===
        frame_top = ttk.Frame(self, padding=10)
        frame_top.pack(fill="x")

        # Entry for new profile name
        self.entry_name = ttk.Entry(frame_top, width=30)
        self.entry_name.pack(side="left", padx=(0, 5))
        
        self.btn_create = ttk.Button(frame_top, text="➕ Create New", style="Accent.TButton", command=self.add_profile)
        self.btn_create.pack(side="left")
        self.btn_import = ttk.Button(frame_top, text="📂 Import", command=self.import_profile)
        self.btn_import.pack(side="right")
        
        # Select All / Refresh Buttons
        ttk.Button(frame_top, text="☑️ Select All", command=self.select_all).pack(side="right", padx=5)
        ttk.Button(frame_top, text="🔄 Refresh", command=self.manual_refresh).pack(side="right", padx=5)
        self.btn_proxy_list = ttk.Button(frame_top, text="📥 Proxy List", command=self.import_proxy_list)
        self.btn_proxy_list.pack(side="right", padx=5)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # === 1.2 FILTER BAR (GROUP FILTER) ===
        self.frame_filter = ttk.Frame(self, padding=(10, 5))
        self.frame_filter.pack(fill="x")

        self.lbl_group_filter = ttk.Label(self.frame_filter, text="📁 Lọc nhóm Profile:", font=("Segoe UI", 10, "bold"))
        self.lbl_group_filter.pack(side="left", padx=(0, 5))

        self.var_group_filter = tk.StringVar(value="Tất cả")
        self.cb_group_filter = ttk.Combobox(self.frame_filter, textvariable=self.var_group_filter, values=["Tất cả"], state="readonly", width=30)
        self.cb_group_filter.pack(side="left", padx=5)
        self.cb_group_filter.bind("<<ComboboxSelected>>", self.on_group_filter_changed)

        # === 1.5 PAGINATION BAR (BOTTOM BAR) ===
        self.frame_pagination = ttk.Frame(self, padding=5)
        self.frame_pagination.pack(fill="x", side="bottom")

        self.btn_prev = ttk.Button(self.frame_pagination, text="⬅️ Trang trước", command=self.prev_page, width=15)
        self.btn_prev.pack(side="left", padx=10)

        self.lbl_page_info = ttk.Label(self.frame_pagination, text="Trang 1 / 1", font=("Segoe UI", 10, "bold"), anchor="center")
        self.lbl_page_info.pack(side="left", fill="x", expand=True)

        self.btn_next = ttk.Button(self.frame_pagination, text="Trang sau ➡️", command=self.next_page, width=15)
        self.btn_next.pack(side="right", padx=10)

        # === 2. LIST AREA (SCROLLABLE AREA) ===
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.scrollbar.pack(side="right", fill="y")

        # Mousewheel scrolling support
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def on_group_filter_changed(self, event=None):
        # Tự động bỏ chọn tất cả profile khi đổi nhóm lọc
        states = ProfileStateManager().get_all_states()
        for name in states.keys():
            ProfileStateManager().set_selected(name, False)
            
        self.current_page = 1
        self.refresh_list()

    def manual_refresh(self):
        """Khôi phục tất cả trạng thái về idle, reset đếm lỗi và tải lại danh sách"""
        ProfileStateManager().reset_all()
        self.refresh_list(force_sync=True)

    def refresh_list(self, force_sync=False):
        """Redraw the entire profile list"""
        # Clear old widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Clear old checkbox data
        self.profile_vars.clear()
        self.card_widgets.clear()

        browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
        if browser_type == "ixBrowser (Local API)":
            self.btn_create.config(state="disabled")
            self.btn_import.config(state="disabled")
            self.btn_proxy_list.config(state="disabled")
            try: self.frame_filter.pack(fill="x", after=self.btn_create.master)
            except: pass
        else:
            self.btn_create.config(state="normal")
            self.btn_import.config(state="normal")
            self.btn_proxy_list.config(state="normal")
            try: self.frame_filter.pack_forget()
            except: pass

        # Đồng bộ hóa danh sách từ thư mục ổ cứng hoặc API chỉ khi force_sync hoặc states trống
        states = ProfileStateManager().get_all_states()
        if force_sync or not states:
            success, error_msg = ProfileStateManager().sync_with_disk()
            if not success and error_msg:
                lbl = ttk.Label(self.scrollable_frame, text=error_msg, foreground="#ff5555", wraplength=500, justify="center")
                lbl.pack(pady=30, padx=20)
                try: self.frame_pagination.pack_forget()
                except: pass
                return
            states = ProfileStateManager().get_all_states()

        # Cập nhật danh sách nhóm vào Combobox nếu chạy chế độ API
        if browser_type == "ixBrowser (Local API)":
            groups = sorted(list(set(state.get("group_name", "").strip() for state in states.values() if state.get("group_name"))))
            cb_values = ["Tất cả"] + groups
            self.cb_group_filter.config(values=cb_values)
            
            # Đảm bảo lựa chọn hiện tại vẫn hợp lệ
            current_selected = self.var_group_filter.get()
            if current_selected not in cb_values:
                self.var_group_filter.set("Tất cả")

        folders = sorted(list(states.keys()))
        
        # Áp dụng bộ lọc nhóm
        if browser_type == "ixBrowser (Local API)":
            selected_group = self.var_group_filter.get()
            if selected_group != "Tất cả":
                folders = [f for f in folders if states[f].get("group_name") == selected_group]

        if not folders:
            if browser_type == "ixBrowser (Local API)":
                selected_group = self.var_group_filter.get()
                if selected_group != "Tất cả":
                    msg = f"Không tìm thấy profile nào trong nhóm '{selected_group}'."
                else:
                    msg = "Không tìm thấy profile nào trên ixBrowser. Vui lòng tạo profile trên ứng dụng ixBrowser trước."
            else:
                msg = "No profiles found. Create new or Import!"
            ttk.Label(self.scrollable_frame, text=msg, foreground="#888", wraplength=500, justify="center").pack(pady=20)
            try: self.frame_pagination.pack_forget()
            except: pass
            return

        # Tính toán phân trang
        import math
        total_profiles = len(folders)
        total_pages = max(1, math.ceil(total_profiles / self.page_size))
        
        if self.current_page > total_pages:
            self.current_page = total_pages
        if self.current_page < 1:
            self.current_page = 1

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_folders = folders[start_idx:end_idx]

        for folder_name in page_folders:
            self.create_profile_card(folder_name)

        # Hiển thị và cập nhật Pagination Bar
        try:
            self.frame_pagination.pack(fill="x", side="bottom")
            self.lbl_page_info.config(text=f"Trang {self.current_page} / {total_pages} (Tổng: {total_profiles} profiles)")
            
            if self.current_page == 1:
                self.btn_prev.config(state="disabled")
            else:
                self.btn_prev.config(state="normal")
                
            if self.current_page == total_pages:
                self.btn_next.config(state="disabled")
            else:
                self.btn_next.config(state="normal")
        except Exception as e:
            print(f"Lỗi vẽ pagination bar: {e}")

    def create_profile_card(self, profile_name):
        """Create UI card for a single profile"""
        browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
        card = ttk.LabelFrame(self.scrollable_frame, padding=(5, 5))
        card.pack(fill="x", expand=True, padx=10, pady=2, anchor="n")

        # --- PROFILE SELECTION CHECKBOX ---
        state_info = ProfileStateManager().get_state(profile_name)
        is_selected = state_info.get("selected", True)
        var = tk.BooleanVar(value=is_selected)
        self.profile_vars[profile_name] = var
        
        def _on_toggle(p=profile_name, v=var):
            ProfileStateManager().set_selected(p, v.get())
            
        chk = ttk.Checkbutton(card, variable=var, command=_on_toggle)
        chk.pack(side="left", padx=5)

        # Icon & Name
        lbl_icon = ttk.Label(card, text="👤", font=("Segoe UI", 12))
        lbl_icon.pack(side="left", padx=5)

        lbl_name = ttk.Label(card, text=profile_name, font=("Segoe UI", 10, "bold"))
        lbl_name.pack(side="left", padx=5)

        # Trạng thái Badge (nhãn hiển thị)
        lbl_status = ttk.Label(card, text="Idle", font=("Segoe UI", 9, "italic"))
        lbl_status.pack(side="left", padx=15)

        # --- RIGHT SIDE: pack buttons first so they claim right space ---
        btn_del = ttk.Button(card, text="🗑️", width=3, command=lambda p=profile_name: self.delete_profile(p))
        if browser_type == "ixBrowser (Local API)":
            btn_del.config(text="❌", command=lambda p=profile_name: self.close_api_profile(p))
        btn_del.pack(side="right", padx=2)

        # Kill button
        def _on_kill(p=profile_name, lbl=lbl_name, _card=card):
            if self.kill_callback:
                self.kill_callback(p)
            else:
                print(f"Kill: Khong co batch dang chay")
            # Cập trạng thái sang bị ép dừng (killed)
            ProfileStateManager().set_state(p, "killed", "Bị người dùng ép dừng bằng nút Kill")
            try:
                lbl.config(foreground="#ff5555")
                btn_kill.config(text="💀", state="disabled")
            except: pass

        btn_kill = ttk.Button(card, text="☠️", width=3, command=_on_kill)
        btn_kill.pack(side="right", padx=2)

        btn_setup = ttk.Button(
            card,
            text="⚙️ Setup",
            style="Accent.TButton",
            command=lambda p=profile_name: self.open_browser_setup(p)
        )
        btn_setup.pack(side="right", padx=2)

        # Display Size (thread) - Chỉ chạy khi không phải API mode
        if browser_type != "ixBrowser (Local API)":
            path = os.path.join(self.profiles_dir, profile_name)
            threading.Thread(target=self._update_size_label, args=(path, card), daemon=True).start()

        # --- PROXY ENTRY (middle, fills remaining space) ---
        entry_proxy = None
        if browser_type in ["ixBrowser", "GoLogin"]:
            current_proxy = ProfileStateManager().get_proxy(profile_name)

            entry_proxy = ttk.Entry(card, width=28)
            if current_proxy:
                entry_proxy.insert(0, current_proxy)
                entry_proxy.config(foreground="white")
            else:
                entry_proxy.insert(0, "host:port:user:pass")
                entry_proxy.config(foreground="#888")
            entry_proxy.pack(side="left", fill="x", expand=True, padx=(10, 5))

            def _focus_in(e):
                if entry_proxy.get() == "host:port:user:pass":
                    entry_proxy.delete(0, tk.END)
                    entry_proxy.config(foreground="white")

            def _focus_out(e):
                val = entry_proxy.get().strip()
                if not val or val == "host:port:user:pass":
                    entry_proxy.delete(0, tk.END)
                    entry_proxy.insert(0, "host:port:user:pass")
                    entry_proxy.config(foreground="#888")
                    ProfileStateManager().set_proxy(profile_name, "")
                else:
                    entry_proxy.config(foreground="white")
                    ProfileStateManager().set_proxy(profile_name, val)

            entry_proxy.bind("<FocusIn>",  _focus_in)
            entry_proxy.bind("<FocusOut>", _focus_out)

        # Đăng ký widget để quản lý trạng thái
        self.card_widgets[profile_name] = {
            "chk": chk,
            "lbl_name": lbl_name,
            "lbl_status": lbl_status,
            "btn_del": btn_del,
            "btn_kill": btn_kill,
            "btn_setup": btn_setup,
            "entry_proxy": entry_proxy
        }

    def _update_size_label(self, path, card_frame):
        """Calculate folder size and update label (Thread safe way)"""
        try:
            size_mb = self.get_size(path)
            # Use after() to update UI from thread
            def _set_label():
                try:
                    if card_frame.winfo_exists():
                        ttk.Label(card_frame, text=f"{size_mb:.1f} MB",
                                  font=("Segoe UI", 8), foreground="#888").pack(side="right", padx=10)
                except Exception:
                    pass
            self.after(0, _set_label)
        except:
            pass


    def get_selected_profiles(self):
        """Return list of selected profile names across all pages"""
        states = ProfileStateManager().get_all_states()
        return [name for name, state in states.items() if state.get("selected", True)]

    def select_all(self):
        """Select all or Deselect all profiles under the active group filter"""
        states = ProfileStateManager().get_all_states()
        browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
        
        # Lấy danh sách profile thuộc bộ lọc nhóm hiện tại
        active_profiles = list(states.keys())
        if browser_type == "ixBrowser (Local API)":
            selected_group = self.var_group_filter.get()
            if selected_group != "Tất cả":
                active_profiles = [name for name in active_profiles if states[name].get("group_name") == selected_group]
                
        any_unchecked = any(not states[name].get("selected", True) for name in active_profiles)
        new_val = True if any_unchecked else False
        
        # Chỉ cập nhật trạng thái chọn cho các profile thuộc nhóm đang lọc
        for name in active_profiles:
            ProfileStateManager().set_selected(name, new_val)
            
        # Cập nhật checkbox hiển thị trên UI
        for name, var in self.profile_vars.items():
            if name in active_profiles:
                var.set(new_val)

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_list()

    def next_page(self):
        states = ProfileStateManager().get_all_states()
        import math
        total_pages = max(1, math.ceil(len(states) / self.page_size))
        if self.current_page < total_pages:
            self.current_page += 1
            self.refresh_list()

    def add_profile(self):
        name = self.entry_name.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a Profile name!")
            return

        invalid_chars = '<>:"/\\|?*'
        if any(char in invalid_chars for char in name):
            messagebox.showerror("Error", "Name cannot contain special characters!")
            return

        new_path = os.path.join(self.profiles_dir, name)
        if os.path.exists(new_path):
            messagebox.showerror("Error", "Name already exists!")
            return

        os.makedirs(new_path)
        self.entry_name.delete(0, tk.END)
        # Đồng bộ hóa với ổ cứng và vẽ lại danh sách
        self.refresh_list(force_sync=True)

    def import_profile(self):
        source_dir = filedialog.askdirectory(title="Select old Profile folder")
        if not source_dir: return

        folder_name = os.path.basename(source_dir)
        if folder_name.lower() in ['user data', 'default', 'profile']:
            folder_name = f"Imported_{int(time.time())}"
        
        dest_path = os.path.join(self.profiles_dir, folder_name)

        if os.path.exists(dest_path):
            try:
                shutil.rmtree(dest_path)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không xóa được bản cũ: {e}")
                return

        # Check if source_dir contains Preferences directly (it's a profile folder Default)
        is_profile_folder = os.path.exists(os.path.join(source_dir, "Preferences"))

        try:
            def copy_task():
                if is_profile_folder:
                    target_default = os.path.join(dest_path, "Default")
                    shutil.copytree(source_dir, target_default)
                else:
                    shutil.copytree(source_dir, dest_path)
                self.after(0, lambda: self.refresh_list(force_sync=True))
            
            threading.Thread(target=copy_task, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    def close_api_profile(self, profile_name):
        parts = profile_name.split(" - ")
        if not parts[0].isdigit():
            return
        profile_id = int(parts[0])
        
        # Gửi API đóng profile
        from utils.ixbrowser_service import IxBrowserService
        IxBrowserService.close_profile(profile_id)
        
        # Giải phóng trạng thái trên Tool về idle
        ProfileStateManager().release(profile_name)
        ProfileStateManager().set_state(profile_name, "idle")
        
        self.refresh_list()

    def delete_profile(self, profile_name):
        state = ProfileStateManager().get_state(profile_name)
        if state.get("status") in ["in_setup", "in_batch"]:
            messagebox.showerror("Lỗi", f"Profile '{profile_name}' đang bận hoạt động, không thể xóa!")
            return

        confirm = messagebox.askyesno("Confirm", f"Permanently delete profile '{profile_name}'?")
        if confirm:
            try:
                shutil.rmtree(os.path.join(self.profiles_dir, profile_name))
                # Đồng bộ hóa
                self.refresh_list(force_sync=True)
            except Exception as e:
                messagebox.showerror("Error", f"Cannot delete: {e}")

    def open_browser_setup(self, profile_name):
        # Checkout chiếm dụng profile
        if not ProfileStateManager().checkout(profile_name, "in_setup"):
            messagebox.showwarning("Cảnh báo", f"Profile '{profile_name}' đang bận sử dụng!")
            return

        profile_path = os.path.join(self.profiles_dir, profile_name)

        async def _run_async():
            print(f"Opening Setup for {profile_name}...")
            context = None
            try:
                context = await init_driver_from_profile_playwright(profile_path, log_callback=print)
                if not context:
                    print("Failed to open browser")
                    ProfileStateManager().set_state(profile_name, "error", "Không thể khởi động trình duyệt")
                    return
                
                # Mở thẳng trang Gemini để setup trên tab đầu tiên (được tự động gắn nhãn tiêu đề profile)
                if context.pages:
                    page = context.pages[0]
                else:
                    page = await context.new_page()
                
                await page.goto("https://gemini.google.com")
                # Giữ browser mở cho đến khi user đóng tất cả tab
                while True:
                    try:
                        if not context.pages:
                            break
                        await asyncio.sleep(1)
                    except:
                        break
                print(f"Setup {profile_name} closed.")
            except Exception as e:
                err_str = str(e).lower()
                if "closed" in err_str or "target page" in err_str or "connection closed" in err_str:
                    print(f"Setup {profile_name} closed by user.")
                else:
                    print(f"Browser Error: {e}")
                    ProfileStateManager().set_state(profile_name, "error", f"Trình duyệt gặp lỗi: {e}")
            finally:
                if context:
                    from engine.browser_ix import close_context_playwright
                    await close_context_playwright(context, print)
                # Đảm bảo luôn giải phóng profile về idle
                ProfileStateManager().release(profile_name)

        def run_browser():
            asyncio.run(_run_async())

        threading.Thread(target=run_browser, daemon=True).start()

    def get_size(self, start_path):
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(start_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except: pass
        return total_size / (1024 * 1024)