import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from datetime import datetime
import sv_ttk
import queue
import os 

from config import DEFAULT_PROFILES
from ui.profile_tab import ProfileManagerTab  
from ui.dashboard_tab import DashboardTab      
from ui.settings_tab import SettingsTab       
from ui.import_tab import ImportProjectTab    
from engine.batch_processor import BatchProcessor 

# Định nghĩa đường dẫn thư mục chứa Profiles
PROFILES_DIR = os.path.join(os.getcwd(), "profiles")
if not os.path.exists(PROFILES_DIR):
    os.makedirs(PROFILES_DIR)

class BatchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 Batch Auto Tool Pro - Realtime Dashboard")
        self.root.geometry("1100x900")
        
        try: sv_ttk.set_theme("dark")
        except: pass

        # Biến trạng thái UI
        self.is_running = False
        self.stop_event = threading.Event()
        
        # 1. Tạo Notebook và các Tab UI TRƯỚC
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # TAB 1: Dashboard & Queue
        self.tab_dashboard = DashboardTab(self.notebook, self) 
        self.notebook.add(self.tab_dashboard, text="📂 Danh sách Dự án")
        
        # TAB 2: Profiles
        self.tab_profiles = ProfileManagerTab(self.notebook, PROFILES_DIR) 
        self.notebook.add(self.tab_profiles, text="👥 Quản lý Profiles")

        # TAB 3: Settings
        self.tab_settings = SettingsTab(self.notebook)
        self.notebook.add(self.tab_settings, text="⚙️ Cài đặt")

        # TAB 4: Import Project
        self.tab_import = ImportProjectTab(self.notebook, self)
        self.notebook.add(self.tab_import, text="📥 Import Project")

        # LOGS
        frame_log = ttk.LabelFrame(self.root, text="📜 Nhật ký hoạt động", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.log_area = scrolledtext.ScrolledText(frame_log, height=10, state='disabled', font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True)
        self._config_log_tags()

        # 2. Khởi tạo Logic Processor
        self.processor = BatchProcessor(
            stop_event=self.stop_event,
            log_callback=self.log,
            update_status_callback=self.update_project_status_callback
        )

        # 3. Lắng nghe sự kiện chuyển Tab (Refresh Gem list)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event):
        """Tự động refresh danh sách Gem khi quay lại Dashboard"""
        selected_tab_id = self.notebook.select()
        if not selected_tab_id: return
        
        selected_widget = self.notebook.nametowidget(selected_tab_id)
        
        if selected_widget == self.tab_dashboard:
            self.tab_dashboard.refresh_gem_list()

    # --- CÁC HÀM GỌI TỪ UI ---
    def on_start_batch(self):
        # 1. Lấy dữ liệu Queue
        queue_data = self.tab_dashboard.project_queue
        if not queue_data:
            messagebox.showwarning("Trống", "Thêm dự án vào list trước!")
            return
        
        mode_text = self.tab_dashboard.selected_mode.get()


        # Map Text sang Key Logic
        mode_map = {
            "SRT ➡ Prompt": "srt_prompt",
            "Prompt ➡ Image": "prompt_image",
            "Image + Prompt ➡ Video": "1_image_prompt_video",
            "Video ➡ Stretch (Timecode)": "stretch_video"
        }
        loop_type = mode_map.get(mode_text, "image_prompt")

        # Tiền kiểm tra cứng cho chế độ Stretch Video
        if loop_type == "stretch_video":
            from utils.file_ops import validate_stretch_videos
            for p in queue_data:
                is_valid, err_msg = validate_stretch_videos(p["input"], p["input2"])
                if not is_valid:
                    self.log(f"❌ Dự án: {os.path.basename(p['input'])} | {err_msg}", "ERROR")
                    return

        # Tiền kiểm tra định dạng Timecode cho chế độ Image+Prompt -> Video
        # Bỏ qua project lỗi, tiếp tục chạy các project còn lại
        if loop_type == "1_image_prompt_video":
            from utils.validators import validate_timecodes
            valid_queue = []
            for i, p in enumerate(queue_data):
                ok, err_msg = validate_timecodes(p["input"])
                if not ok:
                    self.log(f"⚠️ Bỏ qua '{os.path.basename(p['input'])}': Timecode sai định dạng\n{err_msg}", "WARNING")
                    self.update_project_status_callback(i, "Skipped ⏭️")
                else:
                    valid_queue.append(p)

            if not valid_queue:
                self.log("❌ Tất cả project đều bị bỏ qua (timecode sai). Không có gì để chạy.", "ERROR")
                return
            queue_data = valid_queue

        # 3. Lấy Profiles
        profiles = self.tab_profiles.get_selected_profiles()
        if not profiles:
            self.log("❌ Chưa chọn Profile!", "ERROR")
            messagebox.showwarning("Thiếu Profile", "Vui lòng chọn ít nhất 1 Profile!")
            return

        # 4. Setup trạng thái chạy
        self.is_running = True
        self.stop_event.clear()
        self.tab_dashboard.toggle_buttons(is_running=True)

        # 5. Chạy luồng xử lý chính
        t_main = threading.Thread(
            target=self.processor.run_batch_logic,
            args=(queue_data, loop_type, profiles, self.on_batch_finished),
            daemon=True
        )
        t_main.start()

        # 6. Chạy luồng Monitor
        t_monitor = threading.Thread(
            target=self.processor.monitor_loop,
            args=(self.tab_dashboard.update_dashboard_stats,),
            daemon=True
        )
        t_monitor.start()

    def stop_process(self):
        if self.is_running:
            self.log("🛑 Đang dừng... Vui lòng đợi nốt task hiện tại.", "WARNING")
            self.stop_event.set()

    def on_batch_finished(self):
        self.is_running = False
        self.root.after(0, lambda: self._finish_ui_update())

    def _finish_ui_update(self):
        self.tab_dashboard.toggle_buttons(is_running=False)
        if not self.stop_event.is_set():
             self.log("🎉 ĐÃ XONG TẤT CẢ!", "SUCCESS")
             messagebox.showinfo("Xong", "Hoàn thành toàn bộ danh sách!")
        else:
             self.log("🛑 Đã dừng theo yêu cầu.", "WARNING")

    def update_project_status_callback(self, index, status):
        self.root.after(0, lambda: self.tab_dashboard.update_project_status(index, status))

    def _config_log_tags(self):
        self.log_area.tag_config("INFO", foreground="#cccccc")
        self.log_area.tag_config("SUCCESS", foreground="#6cc644")
        self.log_area.tag_config("ERROR", foreground="#ff5555")
        self.log_area.tag_config("WARNING", foreground="#ffb86c")
        self.log_area.tag_config("TECH", foreground="#00d4ff")

    def log(self, message, tag="INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] {message}\n"
        
        def _u():
            self.log_area.config(state='normal')
            self.log_area.insert(tk.END, full_msg, tag)
            self.log_area.see(tk.END)
            self.log_area.config(state='disabled')
            
        self.root.after(0, _u)