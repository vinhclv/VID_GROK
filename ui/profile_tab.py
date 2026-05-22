import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
import threading
import time
import json

import asyncio
from engine.browser_ix  import init_driver_from_profile_playwright

class ProfileManagerTab(ttk.Frame):
    def __init__(self, parent, profiles_dir):
        super().__init__(parent)
        self.profiles_dir = profiles_dir
        
        # Ensure profiles directory exists
        if not os.path.exists(self.profiles_dir):
            os.makedirs(self.profiles_dir)
            
        # Dictionary to store Checkbox variables for each profile
        # Key: Profile Name, Value: tk.BooleanVar
        self.profile_vars = {} 

        self.setup_ui()
        self.refresh_list()

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
        proxy_map = self._load_proxy_map()
        for i, profile in enumerate(profiles):
            proxy_map[profile] = proxies[i % len(proxies)]

        self._save_proxy_map(proxy_map)
        self.refresh_list()

    def _load_proxy_map(self):
        """Đọc proxy_map.json từ thư mục profiles"""
        path = os.path.join(self.profiles_dir, "proxy_map.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _save_proxy_map(self, proxy_map):
        """Ghi proxy_map.json"""
        path = os.path.join(self.profiles_dir, "proxy_map.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(proxy_map, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Khong luu duoc proxy_map: {e}")

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
        ttk.Button(frame_top, text="🔄 Refresh", command=self.refresh_list).pack(side="right", padx=5)
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

    def refresh_list(self):
        """Redraw the entire profile list"""
        # Clear old widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Clear old checkbox data
        self.profile_vars.clear()

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
        var = tk.BooleanVar(value=True)
        self.profile_vars[profile_name] = var
        chk = ttk.Checkbutton(card, variable=var)
        chk.pack(side="left", padx=5)

        # Icon & Name
        lbl_icon = ttk.Label(card, text="👤", font=("Segoe UI", 12))
        lbl_icon.pack(side="left", padx=5)

        lbl_name = ttk.Label(card, text=profile_name, font=("Segoe UI", 10, "bold"))
        lbl_name.pack(side="left", padx=5)

        # --- RIGHT SIDE: pack buttons first so they claim right space ---
        btn_del = ttk.Button(card, text="🗑️", width=3, command=lambda p=profile_name: self.delete_profile(p))
        btn_del.pack(side="right", padx=2)

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
        proxy_map     = self._load_proxy_map()
        current_proxy = proxy_map.get(profile_name, "")

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
            pm  = self._load_proxy_map()
            if not val or val == "host:port:user:pass":
                entry_proxy.delete(0, tk.END)
                entry_proxy.insert(0, "host:port:user:pass")
                entry_proxy.config(foreground="#888")
                pm.pop(profile_name, None)
            else:
                entry_proxy.config(foreground="white")
                pm[profile_name] = val
            self._save_proxy_map(pm)

        entry_proxy.bind("<FocusIn>",  _focus_in)
        entry_proxy.bind("<FocusOut>", _focus_out)

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
        for var in self.profile_vars.values():
            var.set(new_val)

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
        self.refresh_list()

    def import_profile(self):
        source_dir = filedialog.askdirectory(title="Select old Profile folder")
        if not source_dir: return

        folder_name = os.path.basename(source_dir)
        if folder_name.lower() in ['user data', 'default', 'profile']:
            folder_name = f"Imported_{int(time.time())}"
        
        dest_path = os.path.join(self.profiles_dir, folder_name)

        if os.path.exists(dest_path):
            messagebox.showerror("Error", f"Profile '{folder_name}' already exists! Please rename original folder.")
            return

        try:
            def copy_task():
                shutil.copytree(source_dir, dest_path)
                self.after(0, lambda: [messagebox.showinfo("Done", "Import successful!"), self.refresh_list()])
            
            threading.Thread(target=copy_task, daemon=True).start()
            messagebox.showinfo("Notice", "Copying data... Please wait.")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    def delete_profile(self, profile_name):
        confirm = messagebox.askyesno("Confirm", f"Permanently delete profile '{profile_name}'?")
        if confirm:
            try:
                shutil.rmtree(os.path.join(self.profiles_dir, profile_name))
                self.refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Cannot delete: {e}")

    def open_browser_setup(self, profile_name):
        profile_path = os.path.join(self.profiles_dir, profile_name)

        async def _run_async():
            print(f"Opening Setup for {profile_name}...")
            context = await init_driver_from_profile_playwright(profile_path, log_callback=print)
            if not context:
                print("Failed to open browser")
                return
            try:
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
            finally:
                try:
                    await context.close()
                    await context.playwright_instance.stop()
                except: pass

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