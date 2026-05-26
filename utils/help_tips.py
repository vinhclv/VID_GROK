import os
import tkinter as tk
from tkinter import ttk

# ─────────────────────────────────────────────────────────────────────────────
# BẢN ĐỒ DỮ LIỆU HƯỚNG DẪN: Dễ dàng mở rộng thêm tính năng mới tại đây
# ─────────────────────────────────────────────────────────────────────────────
MODE_HELP_DATA = {
    "SRT ➡ Prompt": {
        "title": "SRT ➡ Prompt (Dịch kịch bản bằng AI)",
        "desc": "Tự động phân tích file kịch bản phụ đề SRT gốc thông qua Grok/Gemini AI để dịch thuật và biên soạn thành tệp kịch bản dạng JSON chứa nội dung prompt chi tiết của từng phân cảnh.",
        "input": "📄 File kịch bản phụ đề gốc dạng (.srt)\nVí dụ: movie.srt",
        "output": "📁 Thư mục xuất file JSON kịch bản tổng hợp.\nTên file JSON đầu ra sẽ tự động trùng với tên file SRT phụ đề."
    },
    "Prompt ➡ Image": {
        "title": "Prompt ➡ Image (Vẽ ảnh hàng loạt bằng AI)",
        "desc": "Sử dụng Grok/Gemini AI để vẽ ảnh hàng loạt từ kịch bản JSON. Hỗ trợ tự động tải lên ảnh tham chiếu nhân vật (character) lên khung chat để đảm bảo sự nhất quán tối đa về phong cách hình ảnh.",
        "input": "📄 File kịch bản (.json) có các trường: 'STT', 'prompt', 'character'.\n📸 Thư mục chứa ảnh tham chiếu nhân vật (character/ chứa char1.jpg, char2.jpg...)",
        "output": "📁 Thư mục lưu ảnh thành phẩm đã gen dạng [STT].jpg\n(Hệ thống tự động tạo thư mục con output_image/ để xuất ảnh nếu chọn từ tab import project)."
    },
    "Image + Prompt ➡ Video": {
        "title": "Image + Prompt ➡ Video (Sinh video AI)",
        "desc": "Tạo video phân cảnh AI có độ dài từ 5-10 giây bằng Grok/Gemini từ prompt kịch bản mô tả và các ảnh nhân vật tham chiếu được tải lên.",
        "input": "📄 File kịch bản (.json) có các trường: 'STT', 'prompt', 'character', 'timecode'.\n📸 Thư mục chứa ảnh tham chiếu nhân vật (character/)",
        "output": "📁 Thư mục lưu trữ các video phân cảnh mp4 đã sinh dạng [timecode_start].mp4\n(Hệ thống tự động tạo thư mục con output/ để lưu video nếu chọn từ tab import project)."
    },
    "Video ➡ Stretch (Timecode)": {
        "title": "Video ➡ Stretch (Khớp thời lượng phân cảnh)",
        "desc": "Co kéo hoặc làm chậm/nhanh tốc độ của các file video phân cảnh có sẵn khớp chính xác tuyệt đối 100% với thời lượng quy định trong timecode kịch bản (chạy local bằng FFmpeg). Cuối cùng tự động ghép nối tất cả thành một video tổng hoàn chỉnh.",
        "input": "📄 File kịch bản (.json) có các trường: 'STT', 'timecode'.\n🎬 Thư mục chứa các file video phân cảnh có sẵn (output/)",
        "output": "📁 Thư mục lưu trữ video tổng hoàn chỉnh đã ghép nối\n(Hệ thống tự động tạo thư mục con final/ để lưu video nếu chọn từ tab import project)."
    },
    "Image ➡ Video": {
        "title": "Image ➡ Video (Sinh video từ ảnh tĩnh)",
        "desc": "Sinh video từ ảnh tĩnh kết hợp kịch bản thời lượng timecode bằng công cụ FFmpeg chạy local siêu tốc, không cần qua API/AI.",
        "input": "📄 File kịch bản (.json) có các trường: 'STT', 'timecode'.\n📸 Thư mục chứa ảnh tĩnh của các phân cảnh (output_image/)",
        "output": "📁 Thư mục chứa các video phân cảnh mp4 đã sinh\n(Hệ thống tự động tạo thư mục con output_video/ để  nếu chọn từ tab import project)."
    }
}

class HelpToolTip:
    """
    Hiển thị khung hướng dẫn Obsidian-Dark phẳng cao cấp khi HOVER chuột vào nút ⓘ.
    Không dùng grab_set() hay modal Toplevel để đảm bảo 100% mượt mà, không bị lag.
    """
    def __init__(self, widget, mode_var):
        self.widget = widget
        self.mode_var = mode_var
        self.tip_window = None
        self.id = None
        
        # Ràng buộc các sự kiện rê chuột
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)
        self.widget.bind("<ButtonPress>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window:
            return
        # Đợi 200ms khi hover để tránh bị nhảy liên tục
        self.id = self.widget.after(200, self.display_tip)

    def display_tip(self):
        if self.tip_window:
            return
            
        mode_name = self.mode_var.get()
        data = MODE_HELP_DATA.get(mode_name, {
            "title": f"Hướng dẫn: {mode_name}",
            "desc": "Chưa có mô tả hướng dẫn cho chế độ này.",
            "input": "Chưa rõ định dạng đầu vào.",
            "output": "Chưa rõ định dạng đầu ra."
        })

        # Định vị trí hiển thị ngay bên cạnh/dưới nút ⓘ
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        # Tạo cửa sổ hiển thị borderless không chặn luồng chính
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Viền mỏng xanh Cyan thời thượng bao quanh bóng tối
        tw.config(bg="#121212", highlightbackground="#00d4ff", highlightcolor="#00d4ff", highlightthickness=1)
        
        # Frame đệm lót
        container = tk.Frame(tw, bg="#121212", padx=16, pady=16)
        container.pack(fill="both", expand=True)
        
        # Tiêu đề tính năng
        lbl_title = tk.Label(
            container, 
            text=data["title"], 
            font=("Segoe UI", 10, "bold"), 
            fg="#00d4ff", 
            bg="#121212",
            anchor="w"
        )
        lbl_title.pack(fill="x", pady=(0, 6))
        
        # Vạch ngăn cách mỏng
        sep = tk.Frame(container, bg="#2d2d2d", height=1)
        sep.pack(fill="x", pady=(0, 10))
        
        # Chi tiết mô tả
        lbl_desc = tk.Label(
            container, 
            text=data["desc"], 
            font=("Segoe UI", 9), 
            fg="#bbbbbb", 
            bg="#121212",
            justify=tk.LEFT, 
            anchor="w", 
            wraplength=440
        )
        lbl_desc.pack(fill="x", pady=(0, 12))
        
        # Cấu trúc đầu vào (Input Structure)
        frame_in = tk.Frame(container, bg="#1d1d1f", padx=10, pady=8, highlightbackground="#2d2d2d", highlightthickness=1)
        frame_in.pack(fill="x", pady=(0, 8))
        
        lbl_in_tag = tk.Label(frame_in, text="📥 ĐẦU VÀO (INPUT STRUCTURE)", font=("Segoe UI", 8, "bold"), fg="#ffb86c", bg="#1d1d1f")
        lbl_in_tag.pack(anchor="w")
        
        lbl_in_content = tk.Label(
            frame_in, 
            text=data["input"], 
            font=("Consolas", 8), 
            fg="#e3e3e3", 
            bg="#1d1d1f",
            justify=tk.LEFT, 
            anchor="w", 
            wraplength=410
        )
        lbl_in_content.pack(fill="x", anchor="w", pady=(2, 0))
        
        # Nơi lưu thành phẩm (Output Destination)
        frame_out = tk.Frame(container, bg="#1d1d1f", padx=10, pady=8, highlightbackground="#2d2d2d", highlightthickness=1)
        frame_out.pack(fill="x")
        
        lbl_out_tag = tk.Label(frame_out, text="📤 ĐẦU RA (OUTPUT DESTINATION)", font=("Segoe UI", 8, "bold"), fg="#50fa7b", bg="#1d1d1f")
        lbl_out_tag.pack(anchor="w")
        
        lbl_out_content = tk.Label(
            frame_out, 
            text=data["output"], 
            font=("Consolas", 8), 
            fg="#e3e3e3", 
            bg="#1d1d1f",
            justify=tk.LEFT, 
            anchor="w", 
            wraplength=410
        )
        lbl_out_content.pack(fill="x", anchor="w", pady=(2, 0))

    def hide_tip(self, event=None):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None

def bind_mode_help(widget, mode_var):
    """Liên kết sự kiện hiển thị hướng dẫn khi rê chuột vào widget (Hover)."""
    return HelpToolTip(widget, mode_var)
