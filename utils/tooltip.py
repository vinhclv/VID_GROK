import tkinter as tk

class ToolTip:
    """
    Lớp ToolTip hiện đại sử dụng bóng tối màu bóng bẩy,
    phù hợp 100% với giao diện Dark Theme hiện tại của ứng dụng.
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        
        # Ràng buộc sự kiện chuột
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)
        self.widget.bind("<ButtonPress>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        # Đợi 400ms trước khi hiển thị bóng để tránh spam khi rê chuột nhanh
        self.id = self.widget.after(400, self.display_tip)

    def display_tip(self):
        if self.tip_window:
            return
        
        # Tính toán tọa độ hiển thị (phía dưới widget khoảng 5px)
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        # Tạo cửa sổ borderless độc lập
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        # Giao diện Premium: Nền xám đậm tối màu, chữ xám sáng thanh lịch
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#252526",
            foreground="#cccccc",
            relief=tk.FLAT,
            borderwidth=0,
            padx=10,
            pady=7,
            font=("Segoe UI", 9),
            wraplength=280
        )
        
        # Đường viền mỏng tinh tế màu xám sáng bao quanh bóng
        tw.config(background="#3e3e42")
        label.pack(padx=1, pady=1)

    def hide_tip(self, event=None):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def create_tooltip(widget, text):
    """Hàm tiện ích nhanh để gán nhanh Tooltip cho bất kỳ Widget Tkinter nào."""
    return ToolTip(widget, text)
