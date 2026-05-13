import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import shutil
import threading
import time

from engine.browser import init_driver_from_profile

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

        # --- [IMPORTANT] PROFILE SELECTION CHECKBOX ---
        var = tk.BooleanVar(value=True) # Default checked
        self.profile_vars[profile_name] = var # Save to dict for Main to access
        
        chk = ttk.Checkbutton(card, variable=var)
        chk.pack(side="left", padx=5)
        # ----------------------------------------------

        # Icon & Name
        lbl_icon = ttk.Label(card, text="👤", font=("Segoe UI", 12))
        lbl_icon.pack(side="left", padx=5)

        lbl_name = ttk.Label(card, text=profile_name, font=("Segoe UI", 10, "bold"))
        lbl_name.pack(side="left", padx=5)

        # Action Buttons
        # Delete Button
        btn_del = ttk.Button(card, text="🗑️", width=3, command=lambda p=profile_name: self.delete_profile(p))
        btn_del.pack(side="right", padx=2)

        # Setup Button
        btn_setup = ttk.Button(
            card, 
            text="⚙️ Setup", 
            style="Accent.TButton", 
            command=lambda p=profile_name: self.open_browser_setup(p)
        )
        btn_setup.pack(side="right", padx=2)
        
        # Display Size
        path = os.path.join(self.profiles_dir, profile_name)
        # Run size calculation in thread to avoid UI freeze if many profiles
        threading.Thread(target=self._update_size_label, args=(path, card), daemon=True).start()

    def _update_size_label(self, path, card_frame):
        """Calculate folder size and update label (Thread safe way)"""
        try:
            size_mb = self.get_size(path)
            # Use after() to update UI from thread
            self.after(0, lambda: ttk.Label(card_frame, text=f"{size_mb:.1f} MB", font=("Segoe UI", 8), foreground="#888").pack(side="right", padx=10))
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
        if init_driver_from_profile is None:
             messagebox.showerror("Error", "Browser setup logic not found (Import failed).")
             return

        profile_path = os.path.join(self.profiles_dir, profile_name)
        
        def run_browser():
            print(f"Opening Setup for {profile_name}...")
            driver = init_driver_from_profile(profile_path, log_callback=print)
            
            if driver:
                try:
                    driver.get("https://gemini.google.com")
                    # Loop to keep browser open
                    while True:
                        try:
                            _ = driver.title 
                            time.sleep(1)
                        except:
                            break
                    print(f"Setup {profile_name} closed.")
                except Exception as e:
                    print(f"Browser Error: {e}")
                finally:
                    try: driver.quit()
                    except: pass
            else:
                print("Failed to open driver")

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