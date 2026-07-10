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
        
        ttk.Button(frame_top, text="➕ Create New", style="Accent.TButton", command=self.add_profile).pack(side="left")
        ttk.Button(frame_top, text="📂 Import", command=self.import_profile).pack(side="right")
        
        # Select All / Refresh Buttons
        ttk.Button(frame_top, text="☑️ Select All", command=self.select_all).pack(side="right", padx=5)
        ttk.Button(frame_top, text="🔄 Refresh", command=self.manual_refresh).pack(side="right", padx=5)
        ttk.Button(frame_top, text="📥 Proxy List", command=self.import_proxy_list).pack(side="right", padx=5)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

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

    def manual_refresh(self):
        """Khôi phục tất cả trạng thái về idle, reset đếm lỗi và tải lại danh sách"""
        ProfileStateManager().reset_all()
        self.refresh_list()

    def refresh_list(self):
        """Redraw the entire profile list"""
        # Clear old widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Clear old checkbox data
        self.profile_vars.clear()
        self.card_widgets.clear()

        # Đồng bộ hóa danh sách từ thư mục ổ cứng
        ProfileStateManager().sync_with_disk()

        if os.path.exists(self.profiles_dir):
            folders = sorted([f for f in os.listdir(self.profiles_dir) if os.path.isdir(os.path.join(self.profiles_dir, f))])
            
            if not folders:
                ttk.Label(self.scrollable_frame, text="No profiles found. Create new or Import!", foreground="#888").pack(pady=20)
                return

            for folder_name in folders:
                self.create_profile_card(folder_name)

    def create_profile_card(self, profile_name):
        """Create UI card for a single profile"""
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
        btn_del.pack(side="right", padx=2)

        # Kill button
        def _on_kill(p=profile_name, lbl=lbl_name, _card=card):
            if self.kill_callback:
                self.kill_callback(p)
            else:
                print(f"Kill: Khong co batch dang chay")
            # Cập nhật trạng thái sang bị ép dừng (killed)
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

        # Display Size (thread)
        path = os.path.join(self.profiles_dir, profile_name)
        threading.Thread(target=self._update_size_label, args=(path, card), daemon=True).start()

        # --- PROXY ENTRY (middle, fills remaining space) ---
        browser_type = config.global_settings["system"].get("browser_type", "ixBrowser")
        entry_proxy = None
        if browser_type == "ixBrowser":
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
        """Return list of selected profile names"""
        return [name for name, var in self.profile_vars.items() if var.get()]

    def select_all(self):
        """Select all or Deselect all"""
        any_unchecked = any(not var.get() for var in self.profile_vars.values())
        new_val = True if any_unchecked else False
        for name, var in self.profile_vars.items():
            var.set(new_val)
            ProfileStateManager().set_selected(name, new_val)

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
        ProfileStateManager().sync_with_disk()
        self.refresh_list()

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

        try:
            def copy_task():
                shutil.copytree(source_dir, dest_path)
                ProfileStateManager().sync_with_disk()
                self.after(0, self.refresh_list)
            
            threading.Thread(target=copy_task, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

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
                ProfileStateManager().sync_with_disk()
                self.refresh_list()
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
            context = await init_driver_from_profile_playwright(profile_path, log_callback=print)
            if not context:
                print("Failed to open browser")
                ProfileStateManager().set_state(profile_name, "error", "Không thể khởi động trình duyệt")
                return
            try:
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
                print(f"Browser Error: {e}")
                ProfileStateManager().set_state(profile_name, "error", f"Trình duyệt gặp lỗi: {e}")
            finally:
                try:
                    await context.close()
                    await context.playwright_instance.stop()
                except: pass
                # Giải phóng profile về idle
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