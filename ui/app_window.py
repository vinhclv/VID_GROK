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

from utils.profile_state import ProfileStateManager

# Định nghĩa đường dẫn thư mục chứa Profiles
PROFILES_DIR = os.path.join(os.getcwd(), "profiles")
if not os.path.exists(PROFILES_DIR):
    os.makedirs(PROFILES_DIR)

class BatchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🚀 Batch Auto Tool Pro - Realtime Dashboard")
        self.root.geometry("1100x900")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Reset trạng thái các profile về idle lúc khởi động
        ProfileStateManager().reset_all()
        
        # Khởi chạy phân quyền Sandbox ngầm tránh treo giao diện
        try:
            from engine.browser_ix import fix_sandbox_permissions_async
            fix_sandbox_permissions_async(log_callback=self.log)
        except Exception as e:
            print(f"Lỗi khởi chạy phân quyền Sandbox ngầm: {e}")
        
        try: sv_ttk.set_theme("dark")
        except: pass

        # Biến trạng thái UI
        self.is_running = False
        self.stop_event = threading.Event()
        
        # Tạo PanedWindow dọc để phân tách Notebook và Logs, cho phép kéo giãn bằng chuột
        main_pane = ttk.PanedWindow(self.root, orient="vertical")
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        # 1. Tạo Notebook và các Tab UI TRƯỚC
        self.notebook = ttk.Notebook(main_pane)
        main_pane.add(self.notebook, weight=3)
        
        # TAB 1: Dashboard & Queue
        self.tab_dashboard = DashboardTab(self.notebook, self) 
        self.notebook.add(self.tab_dashboard, text="📂 Danh sách Dự án")
        
        # TAB 2: Profiles
        self.tab_profiles = ProfileManagerTab(
            self.notebook,
            PROFILES_DIR,
            kill_callback=self._on_kill_profile
        )
        self.notebook.add(self.tab_profiles, text="👥 Quản lý Profiles")

        # TAB 3: Settings
        self.tab_settings = SettingsTab(self.notebook)
        self.notebook.add(self.tab_settings, text="⚙️ Cài đặt")

        # TAB 4: Import Project
        self.tab_import = ImportProjectTab(self.notebook, self)
        self.notebook.add(self.tab_import, text="📥 Import Project")

        # LOGS
        frame_log = ttk.LabelFrame(main_pane, text="📜 Nhật ký hoạt động", padding=10)
        main_pane.add(frame_log, weight=1)
        
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
        elif selected_widget == self.tab_profiles:
            self.tab_profiles.refresh_list()
        elif selected_widget == self.tab_import:
            self.tab_import.refresh_gem_list()

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
            "Video ➡ Stretch (Timecode)": "stretch_video",
            "Image ➡ Video": "image_to_video"
        }
        loop_type = mode_map.get(mode_text, "image_prompt")

        # Tiền kiểm tra cứng cho chế độ Stretch Video
        if loop_type == "stretch_video":
            from utils.file_ops import validate_stretch_videos
            for i, p in enumerate(queue_data):
                is_valid, err_msg = validate_stretch_videos(p["input"], p["input2"])
                if not is_valid:
                    self.log(f"⚠️ Bỏ qua '{os.path.basename(p['input'])}': {err_msg}", "WARNING")
                    self.update_project_status_callback(i, "Failed ❌")

        # Tiền kiểm tra cứng cho chế độ Image -> Video (Local FFmpeg)
        if loop_type == "image_to_video":
            from utils.file_ops import validate_image_to_video
            for i, p in enumerate(queue_data):
                is_valid, err_msg = validate_image_to_video(p["input"], p["input2"])
                if not is_valid:
                    self.log(f"⚠️ Bỏ qua '{os.path.basename(p['input'])}': {err_msg}", "WARNING")
                    self.update_project_status_callback(i, "Failed ❌")

        # Tiền kiểm tra định dạng Timecode cho các chế độ có timecode
        # Bỏ qua project lỗi, tiếp tục chạy các project còn lại
        if loop_type in ["1_image_prompt_video", "image_to_video"]:
            from utils.validators import validate_timecodes
            for i, p in enumerate(queue_data):
                # Nếu dự án đã bị đánh dấu Failed từ bước trước, bỏ qua kiểm tra timecode
                if p.get("status") == "Failed ❌":
                    continue
                ok, err_msg = validate_timecodes(p["input"])
                if not ok:
                    self.log(f"⚠️ Bỏ qua '{os.path.basename(p['input'])}': Timecode sai định dạng\n{err_msg}", "WARNING")
                    self.update_project_status_callback(i, "Skipped ⏭️")

        # Kiểm tra xem có ít nhất 1 project ở trạng thái Waiting để chạy
        has_runnable = any(p.get("status", "Waiting") == "Waiting" for p in queue_data)
        if not has_runnable:
            self.log("❌ Không có dự án nào hợp lệ để chạy trong hàng chờ.", "ERROR")
            return

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

        # 6. Chạy luồng Monitor (đảm bảo cập nhật UI trên main thread bằng after)
        t_monitor = threading.Thread(
            target=self.processor.monitor_loop,
            args=(self.update_dashboard_stats_safe,),
            daemon=True
        )
        t_monitor.start()

    def _on_kill_profile(self, profile_name):
        """Callback từ Profile Tab khi user click ☠️"""
        if self.is_running and hasattr(self, 'processor'):
            self.processor.kill_profile_now(profile_name)
        else:
            self.log(f"⚠️ Kill '{profile_name}': Không có batch nào đang chạy.", "WARNING")

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

    def on_close(self):
        self.stop_event.set()
        try:
            self.root.destroy()
        except Exception:
            pass

    def update_dashboard_stats_safe(self, total, pending, done):
        try:
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.tab_dashboard.update_dashboard_stats(total, pending, done))
        except Exception:
            pass

    def update_project_status_callback(self, index, status):
        try:
            if self.root.winfo_exists():
                self.root.after(0, lambda: self.tab_dashboard.update_project_status(index, status))
        except Exception:
            pass

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
            try:
                if not self.root.winfo_exists(): return
                self.log_area.config(state='normal')
                self.log_area.insert(tk.END, full_msg, tag)
                self.log_area.see(tk.END)
                self.log_area.config(state='disabled')
            except Exception:
                pass
            
        try:
            if self.root.winfo_exists():
                self.root.after(0, _u)
        except Exception:
            pass