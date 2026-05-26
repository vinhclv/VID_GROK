# main.py
import sys
import warnings
import tkinter as tk
from ui.app_window import BatchApp

# Bỏ qua các ngoại lệ vô hại khi đóng ứng dụng trên Windows (lỗi đóng luồng asyncio/Proactor)
def silence_unraisable_hook(unraisable):
    exc_type = unraisable.exc_type
    exc_value = unraisable.exc_value
    
    # Bỏ qua lỗi "I/O operation on closed pipe" và "Event loop is closed" khi exit
    if exc_type is ValueError and "I/O operation on closed pipe" in str(exc_value):
        return
    if exc_type is RuntimeError and "Event loop is closed" in str(exc_value):
        return
    
    sys.__unraisablehook__(unraisable)

sys.unraisablehook = silence_unraisable_hook

# Tắt cảnh báo ResourceWarning từ các tiến trình con đóng chậm
warnings.filterwarnings("ignore", category=ResourceWarning)


if __name__ == "__main__":
    root = tk.Tk()
    app = BatchApp(root)
    root.mainloop()